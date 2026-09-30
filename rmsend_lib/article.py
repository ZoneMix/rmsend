"""Readable-article extraction and the DOM surgery that makes it read well on e-ink.

Everything here is generic HTML work except the source dispatch in `fetch_article`.
The transforms preserve nested footnote anchors, heading hierarchy and figure
captions that general article extraction can otherwise lose.
"""

from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import NoReturn

import mimetypes

import requests
import trafilatura
from lxml import etree
from lxml import html as lxml_html

from rmsend_lib import config


@dataclass(frozen=True)
class Article:
    title: str
    subtitle: str
    author: str
    published: str
    html: str


def die(message: str) -> NoReturn:
    print(f"rmsend: {message}", file=sys.stderr)
    raise SystemExit(1)


def safe_stem(title: str) -> str:
    cleaned = " ".join(config.FILENAME_SAFE.sub(" ", title).split()) or "article"
    return cleaned[:config.MAX_STEM]


# --- restructuring ---------------------------------------------------------


def drop_boilerplate(body) -> int:
    doomed = [
        p for p in body.iter("p")
        if any(rx.search((p.text_content() or "").strip()) for rx in config.BOILERPLATE)
    ]
    for p in doomed:
        p.getparent().remove(p)
    return len(doomed)


def _fetch_image(session: requests.Session, src: str) -> tuple[bytes, str] | None:
    try:
        response = session.get(src, timeout=config.FETCH_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    suffix = mimetypes.guess_extension(content_type) or ".jpg"
    return response.content, (".jpg" if suffix == ".jpe" else suffix)


def _remove_image(img) -> None:
    # A broken image box is worse than no image, so drop the whole figure.
    parent = img.getparent()
    doomed = parent if parent is not None and parent.tag == "figure" else img
    if doomed.getparent() is not None:
        doomed.getparent().remove(doomed)


def localize_images(body, workdir: Path) -> tuple[int, int]:
    """Pull images down beside the page so rendering needs no network and is repeatable."""
    media = workdir / "media"
    media.mkdir(exist_ok=True)
    remote = [
        (index, img) for index, img in enumerate(list(body.iter("img")))
        if (img.get("src") or "").startswith(("http://", "https://"))
    ]
    if not remote:
        return 0, 0
    with requests.Session() as session:
        session.headers["User-Agent"] = config.USER_AGENT
        with ThreadPoolExecutor(max_workers=config.IMAGE_WORKERS) as pool:
            results = list(pool.map(lambda pair: _fetch_image(session, pair[1].get("src")), remote))
    saved, failed = 0, 0
    for (index, img), result in zip(remote, results):
        if result is None:
            _remove_image(img)
            failed += 1
            continue
        payload, suffix = result
        target = media / f"image{index}{suffix}"
        target.write_bytes(payload)
        img.set("src", f"{media.name}/{target.name}")
        saved += 1
    return saved, failed


def unwrap_legacy_anchors(body) -> int:
    """Some publishers wrap footnote markers in an <a>, nesting it around the inner
    footnote link. Nested anchors are invalid, so the parser re-parents the inner one
    out of its <sup> and the superscript styling stops matching."""
    unwrapped = 0
    for anchor in list(body.iter("a")):
        if config.LEGACY_FOOTNOTE_HREF.search(anchor.get("href") or ""):
            anchor.drop_tag()
            unwrapped += 1
    return unwrapped


def harvest_captions(source_html: str) -> dict[str, str]:
    """Readability extraction drops <figcaption>, so take captions from the source page."""
    if not (source_html or "").strip():
        return {}
    try:
        doc = lxml_html.fromstring(source_html)
    except (ValueError, SyntaxError, etree.ParserError):
        return {}
    captions: dict[str, str] = {}
    for figure in doc.iter("figure"):
        caption = figure.find(".//figcaption")
        if caption is None:
            continue
        text = " ".join((caption.text_content() or "").split())
        if not text:
            continue
        for img in figure.iter("img"):
            src = img.get("src")
            if src:
                captions[src] = text
    return captions


def caption_for(src: str, captions: dict[str, str]) -> str:
    if src in captions:
        return captions[src]
    tail = src.rsplit("/", 1)[-1]
    for known, text in captions.items():
        if tail and known.endswith(tail):
            return text
    return ""


def demote_headings(body) -> int:
    """Extractors flatten every section heading to h1, which fragments the output."""
    headings = [el for el in body.iter() if isinstance(el.tag, str)
                and re.fullmatch(r"h[1-5]", el.tag)]
    for el in headings:
        el.tag = f"h{int(el.tag[1]) + 1}"
    return len(headings)


def _stray_credit(figure):
    """Credit lines often say nothing in their text; the licence link gives them away."""
    nxt = figure.getnext()
    if nxt is None or nxt.tag != "p":
        return None
    text = (nxt.text_content() or "").strip()
    hints = text + " " + " ".join(nxt.xpath(".//@href"))
    if text and len(text) <= config.MAX_CAPTION_CHARS and config.CAPTION_HINT.search(hints):
        return nxt
    return None


def wrap_figures(body, captions: dict[str, str]) -> tuple[int, int]:
    wrapped, captioned = 0, 0
    for img in list(body.iter("img")):
        parent = img.getparent()
        if parent is None or parent.tag == "figure":
            continue
        figure = lxml_html.Element("figure")
        lone_wrapper = (
            parent.tag == "p" and len(parent) == 1 and not (parent.text or "").strip()
        )
        anchor = parent if lone_wrapper else img
        anchor.addprevious(figure)
        figure.append(img)
        if anchor is not img and anchor.getparent() is not None:
            anchor.getparent().remove(anchor)

        stray = _stray_credit(figure)
        real = caption_for(img.get("src") or "", captions)
        if real:
            caption = lxml_html.Element("figcaption")
            caption.text = real
            figure.append(caption)
            captioned += 1
            if stray is not None:
                stray.getparent().remove(stray)
        elif stray is not None:
            stray.tag = "figcaption"
            figure.append(stray)
            captioned += 1
        wrapped += 1
    return wrapped, captioned


def wrap_quotations(body) -> int:
    """A short paragraph followed by a dashed attribution is a pulled quotation."""
    wrapped = 0
    for para in list(body.iter("p")):
        text = (para.text_content() or "").strip()
        if not config.ATTRIBUTION.match(text) or len(text) > config.MAX_ATTRIBUTION_CHARS:
            continue
        quote = para.getprevious()
        if quote is None or quote.tag != "p":
            continue
        if len((quote.text_content() or "").strip()) > config.MAX_QUOTE_CHARS:
            continue
        block = lxml_html.Element("blockquote")
        quote.addprevious(block)
        para.set("class", "attribution")
        block.append(quote)
        block.append(para)
        wrapped += 1
    return wrapped


def collect_endnotes(body) -> dict[str, object]:
    return {
        m.group(1): p
        for p in body.iter("p")
        if (m := config.ENDNOTE_MARKER.match((p.text_content() or "").strip()))
    }


def link_footnotes(body, endnotes: dict[str, object]) -> int:
    """Turn <sup>[12]</sup> markers into links to the matching endnote, and back."""
    notes = set(endnotes.values())
    linked = 0
    for sup in list(body.iter("sup")):
        label = (sup.text_content() or "").strip()
        match = config.FOOTNOTE_REF.match(label)
        if not match or match.group(1) not in endnotes:
            continue
        # Each number also appears as the endnote's own leading marker; leave that alone.
        if any(ancestor in notes for ancestor in sup.iterancestors()):
            continue
        number = match.group(1)
        link = lxml_html.Element("a")
        link.set("href", f"#fn-{number}")
        link.set("id", f"fnref-{number}")
        link.text = label
        for child in list(sup):
            sup.remove(child)
        sup.text = None
        sup.append(link)
        linked += 1

    for number, note in endnotes.items():
        # pandoc's AST gives paragraphs no attribute slot, so the id rides on a span.
        anchor = lxml_html.Element("span")
        anchor.set("id", f"fn-{number}")
        anchor.text = note.text
        note.text = None
        for child in list(note):
            note.remove(child)
            anchor.append(child)
        note.append(anchor)
        back = lxml_html.Element("a")
        back.set("href", f"#fnref-{number}")
        back.text = " ↩"
        note.append(back)
    return linked


def group_endnotes(body, endnotes: dict[str, object]) -> bool:
    """Move a trailing run of endnote paragraphs into their own titled section."""
    notes = set(endnotes.values())
    run: list = []
    for el in reversed([el for el in body if isinstance(el.tag, str)]):
        if el in notes:
            run.append(el)
        elif el.tag == "p" and not (el.text_content() or "").strip():
            continue
        else:
            break
    if len(run) < 2:
        return False

    run.reverse()
    section = lxml_html.Element("section")
    section.set("class", "endnotes")
    heading = lxml_html.Element("h2")
    heading.text = "Notes"
    section.append(heading)
    run[0].addprevious(section)
    for note in run:
        section.append(note)
    return True


def restructure(article_html: str, source_html: str, workdir: Path) -> tuple[str, str]:
    doc = lxml_html.fromstring(article_html)
    body = doc.find("body")
    if body is None:
        body = doc

    dropped = drop_boilerplate(body)
    unwrap_legacy_anchors(body)
    headings = demote_headings(body)
    figures, captioned = wrap_figures(body, harvest_captions(source_html))
    saved, failed = localize_images(body, workdir)
    quotes = wrap_quotations(body)
    endnotes = collect_endnotes(body)
    linked = link_footnotes(body, endnotes)
    sectioned = group_endnotes(body, endnotes)

    parts = [f"{headings} headings demoted", f"{saved} images",
             f"{figures} figures ({captioned} captioned)", f"{quotes} quotations"]
    if failed:
        parts.append(f"{failed} images unreachable")
    if linked:
        parts.append(f"{linked} footnotes linked")
    if sectioned:
        parts.append(f"{len(endnotes)} endnotes sectioned")
    if dropped:
        parts.append(f"{dropped} boilerplate removed")

    inner = "".join(lxml_html.tostring(child, encoding="unicode") for child in body)
    return inner, ", ".join(parts)


# --- extraction ------------------------------------------------------------


def format_published(raw: str) -> str:
    try:
        return date.fromisoformat(raw[:10]).strftime("%-d %B %Y")
    except ValueError:
        return raw


def fetch_article(url: str, workdir: Path, *, original: bool = False) -> Article:
    from rmsend_lib.mere_orthodoxy import fetch_reader, handles

    if handles(url):
        return fetch_reader(url, workdir, original=original)
    try:
        response = requests.get(url, timeout=config.FETCH_TIMEOUT,
                                headers={"User-Agent": config.USER_AGENT})
        response.raise_for_status()
    except requests.RequestException as exc:
        die(f"could not fetch {url}: {exc}")

    source = response.text
    body = trafilatura.extract(
        source, output_format="html", include_images=True, include_links=True,
        include_formatting=True, include_tables=True, with_metadata=False, url=url,
    )
    if not body:
        die(f"no readable article found at {url}")

    cleaned, report = restructure(body, source, workdir)
    print(f"restructured: {report}")

    meta = trafilatura.extract_metadata(source, default_url=url)
    published = (getattr(meta, "date", None) or "").strip()
    return Article(
        title=(getattr(meta, "title", None) or url).strip(),
        subtitle=(getattr(meta, "description", None) or "").strip(),
        author=(getattr(meta, "author", None) or getattr(meta, "sitename", None) or "").strip(),
        published=format_published(published) if published else "",
        html=cleaned,
    )
