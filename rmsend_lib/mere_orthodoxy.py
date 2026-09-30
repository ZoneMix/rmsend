"""The Faith Received's public JSON readers, without JavaScript or an LLM.

Classic works use ordered page shards; EEBO works use a nested division tree.
These are the same public data sources used by the site's reader, not an API
for access-controlled articles. Unsupported formats fail rather than sending UI.
"""
from __future__ import annotations

import gzip
import html
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

import requests
from lxml import etree, html as dom
from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

from rmsend_lib import config
from rmsend_lib.article import Article, die, localize_images

SITE = "https://mereorthodoxy.com"
LIBRARY = "https://mo-tfr-library.mo-podcast-feed.workers.dev"
SLUGS = SITE + "/assets/data/faith-received/public-slugs.json"
SLUG_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,199}\Z")
FILE_PATTERN = re.compile(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]*\.json(?:\.gz)?\Z")
ALLOWED_TAGS = frozenset("p h2 h3 h4 h5 h6 em i strong b sup sub blockquote ul ol li br hr "
                         "a img figure figcaption table thead tbody tr th td section span code pre".split())
ACTIVE_TAGS = frozenset("script style iframe object embed form input button link meta svg math".split())


def handles(url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.hostname in {"mereorthodoxy.com", "www.mereorthodoxy.com"}
            and parsed.path.rstrip("/") == "/the-faith-received/read")


def read_json(url: str, *, optional: bool = False) -> dict | None:
    try:
        response = requests.get(url, timeout=config.FETCH_TIMEOUT, headers={"User-Agent": config.USER_AGENT})
        if optional and response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.content
        if payload.startswith(b"\x1f\x8b"):
            payload = gzip.decompress(payload)
        result = json.loads(payload)
    except (requests.RequestException, OSError, EOFError, ValueError) as exc:
        die(f"Mere Orthodoxy data unavailable at {url}: {exc}")
    if not isinstance(result, dict):
        die(f"Mere Orthodoxy returned an unexpected JSON schema at {url}")
    return result


def clean_html(fragment: str, base: str, prefix: str) -> str:
    """Keep book structure, prose and notes; remove executable content and UI markers."""
    try:
        root = dom.fragment_fromstring(fragment, create_parent="section")
    except (etree.ParserError, ValueError) as exc:
        die(f"Mere Orthodoxy returned invalid book markup: {exc}")
    for element in list(root.iterdescendants()):
        if not isinstance(element.tag, str):
            element.drop_tree()
            continue
        tag = element.tag.lower()
        if tag in ACTIVE_TAGS:
            element.drop_tree()
            continue
        if element.getparent() is None:
            continue
        if tag == "h1":
            element.tag = tag = "h2"
        if tag not in ALLOWED_TAGS or "pb" in (element.get("class") or "").split():
            element.drop_tag()
            continue
        attributes = dict(element.attrib)
        element.attrib.clear()
        if attributes.get("id"):
            element.set("id", prefix + attributes["id"])
        if "note" in attributes.get("class", "").split():
            element.set("class", "source-note")
        for name in ("href", "src"):
            value = attributes.get(name)
            if not value:
                continue
            if name == "href" and value.startswith("#"):
                element.set(name, "#" + prefix + value[1:])
            else:
                absolute = urljoin(base, value)
                if urlsplit(absolute).scheme in {"http", "https"}:
                    element.set(name, absolute)
        for name in ("alt", "title", "colspan", "rowspan", "start"):
            if name in attributes:
                element.set(name, attributes[name])
    return (html.escape(root.text or "")
            + "".join(dom.tostring(child, encoding="unicode") for child in root))


def markdown(source: str, base: str, prefix: str) -> str:
    parser = MarkdownIt("commonmark", {"html": True}).enable("table").use(footnote_plugin)
    return clean_html(parser.render(source), base, prefix)


def classic(slug: str) -> tuple[dict, str]:
    base = LIBRARY + "/v1/works/" + quote(slug, safe="") + "/"
    meta = read_json(base + "meta.json")
    files = ([meta["single"]] if meta.get("single") else
             [part.get("file") for part in meta.get("shards", []) if isinstance(part, dict)])
    if not files:
        die("this Mere Orthodoxy work uses a TEI reader; this exporter supports classic JSON and EEBO works")
    pages = []
    for filename in files:
        if not isinstance(filename, str) or not FILE_PATTERN.fullmatch(filename) or ".." in filename:
            die("Mere Orthodoxy returned an unsafe shard filename")
        shard = read_json(base + filename)
        if not isinstance(shard.get("pages"), list):
            die(f"Mere Orthodoxy shard {filename} has no page list")
        pages.extend(shard["pages"])
    if not pages or (meta.get("n_pages") is not None and len(pages) != meta["n_pages"]):
        die("Mere Orthodoxy page count changed or a shard is incomplete; refusing a partial export")
    seen = set()
    parts = []
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or page.get("n") in seen:
            die("Mere Orthodoxy returned invalid or duplicate pages")
        seen.add(page.get("n"))
        text = page.get("en")
        if not isinstance(text, str) or not text.strip():
            die(f"Mere Orthodoxy page {page.get('n')} has no English text; refusing a partial export")
        parts.append(markdown(text, base, f"part-{index}-"))
    print(f"Mere Orthodoxy: classic reader, all {len(pages)} source sections/pages")
    return meta, "\n".join(parts)


def eebo(slug: str, *, original: bool) -> tuple[dict, str]:
    identifier = slug.removeprefix("eebo-")
    if not identifier.isdigit():
        die("invalid Mere Orthodoxy EEBO identifier")
    base = LIBRARY + "/eebo/"
    data = read_json(base + identifier + ".json.gz")
    modern = None if original else read_json(LIBRARY + "/eebo_modern/" + identifier + ".json.gz", optional=True)
    replacements = (modern or {}).get("m", {})
    if not isinstance(replacements, dict) or not isinstance(data.get("toc"), list):
        die("Mere Orthodoxy returned an unexpected EEBO division schema")
    counts = {"source": 0, "modern": 0}

    def walk(nodes: list, parent: str = "", depth: int = 0) -> list[str]:
        if depth > 30:
            die("Mere Orthodoxy division tree exceeds the supported nesting depth")
        parts = []
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                die("Mere Orthodoxy returned an invalid EEBO division")
            path = f"{parent}.{index}" if parent else str(index)
            label = node.get("label", "")
            source = node.get("html", "")
            if not isinstance(label, str) or not isinstance(source, str):
                die("Mere Orthodoxy returned invalid EEBO text")
            heading = min(2 + depth, 6)
            heading_html = f"<h{heading}>{html.escape(label.replace('_', ' '))}</h{heading}>" if label else ""
            if source.strip():
                replacement = replacements.get(path)
                if replacement is not None and not isinstance(replacement, str):
                    die("Mere Orthodoxy returned invalid modern English text")
                if replacement is not None and not replacement.strip():
                    die("Mere Orthodoxy returned an empty modernized division; refusing a partial export")
                text = replacement if replacement is not None else source
                counts["modern" if replacement is not None else "source"] += 1
                prefix = f"part-{path}-"
                rendered = (clean_html(text, base, prefix) if re.search(r"<[a-zA-Z][^>]*>", text)
                            else markdown(text, base, prefix))
                # A division label often repeats the book's own opening heading.
                # Retain the source heading and avoid inserting a second copy.
                content = dom.fragment_fromstring(rendered, create_parent="section")
                first = content[0] if len(content) else None
                if (label and first is not None and not (content.text or "").strip()
                        and " ".join(first.text_content().split()).casefold()
                        == " ".join(label.replace("_", " ").split()).casefold()):
                    first.tag = f"h{heading}"
                    heading_html = ""
                    rendered = "".join(dom.tostring(child, encoding="unicode") for child in content)
                parts.extend([heading_html, rendered])
            elif heading_html:
                parts.append(heading_html)
            children = node.get("kids", [])
            if not isinstance(children, list):
                die("Mere Orthodoxy returned an invalid child division list")
            parts.extend(walk(children, path, depth + 1))
        return parts

    parts = walk(data["toc"])
    if not sum(counts.values()):
        die("Mere Orthodoxy EEBO work has no readable divisions")
    print(f"Mere Orthodoxy: EEBO reader, {counts['source']} original and {counts['modern']} modernized divisions")
    meta = data.get("meta")
    if not isinstance(meta, dict):
        die("Mere Orthodoxy EEBO work has no metadata")
    return meta, "\n".join(parts)


def fetch_reader(url: str, workdir: Path, *, original: bool = False) -> Article:
    params = parse_qs(urlsplit(url).query)
    slug = (params.get("w") or params.get("ws") or [""])[0]
    if not SLUG_PATTERN.fullmatch(slug):
        die("Mere Orthodoxy reader URLs need one valid ?w=work-slug")
    public_slugs = read_json(SLUGS).get("works")
    if not isinstance(public_slugs, dict):
        die("Mere Orthodoxy's public slug map changed; refusing to guess the work")
    internal = next((key for key, value in public_slugs.items() if value == slug), slug)
    if not isinstance(internal, str) or not SLUG_PATTERN.fullmatch(internal):
        die("Mere Orthodoxy returned an invalid internal work identifier")
    if internal.startswith(("pg-", "pld-", "po-")):
        die("this Mere Orthodoxy work uses a TEI corpus; this exporter supports classic JSON and EEBO works")
    meta, body = eebo(internal, original=original) if internal.startswith("eebo-") else classic(internal)
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip():
        die("Mere Orthodoxy work has no title")
    root = dom.fragment_fromstring(body, create_parent="article")
    saved, failed = localize_images(root, workdir)
    if failed:
        die(f"{failed} Mere Orthodoxy images could not be fetched; refusing an incomplete export")
    body = dom.tostring(root, encoding="unicode")
    source_url = SITE + "/the-faith-received/read/?" + urlencode({"w": slug})
    body += f'<p class="source-credit">Source: <a href="{html.escape(source_url, quote=True)}">Mere Orthodoxy · The Faith Received</a></p>'
    print(f"Mere Orthodoxy: {saved} images saved; navigation parameters ignored, whole work exported")
    return Article(title=title.strip(), subtitle="", author=str(meta.get("author") or ""),
                   published=str(meta.get("volume") or meta.get("year") or ""), html=body)
