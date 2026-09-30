"""Rendering: HTML → PDF through headless Chrome, HTML → EPUB through pandoc.

Standard library only. `print_html_to_pdf` is the reusable core — the Daily Paper hands it a
finished HTML file — while `build_pdf` wraps an extracted Article in the article template.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

from rmsend_lib import config

_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def die(message: str) -> NoReturn:
    print(f"rmsend: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_css(name: str) -> str:
    path = config.ASSET_DIR / name
    if not path.is_file():
        die(f"missing stylesheet {path}")
    return path.read_text(encoding="utf-8")


def find_chrome() -> str:
    for candidate in config.CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    # Ubuntu's AppArmor profile supports the system Chrome installation; an
    # unrelated Chromium build on PATH may lack a usable sandbox.
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    die("no Chrome or Chromium found; install one or use --format epub")


def html_title(document: Path) -> str:
    """The <title> of a local HTML file, else its stem."""
    try:
        head = document.read_text(encoding="utf-8", errors="replace")[:20000]
    except OSError:
        return document.stem
    match = _TITLE_TAG.search(head)
    text = html.unescape(" ".join(match.group(1).split())) if match else ""
    return text or document.stem


def render_document(article, css: str) -> str:
    def line(css_class: str, text: str) -> str:
        return f'<p class="{css_class}">{html.escape(text)}</p>' if text else ""

    return config.DOCUMENT_TEMPLATE.format(
        css=css,
        title=html.escape(article.title),
        subtitle=line("subtitle", article.subtitle),
        byline=line("byline", article.author),
        dateline=line("dateline", article.published),
        body=article.html,
    )


def pdf_is_complete(pdf: Path) -> bool:
    if not pdf.is_file():
        return False
    size = pdf.stat().st_size
    if size < config.MIN_PDF_BYTES:
        return False
    with pdf.open("rb") as handle:
        handle.seek(-min(config.PDF_TRAILER_WINDOW, size), os.SEEK_END)
        return b"%%EOF" in handle.read()


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=config.PROBE_TIMEOUT)
        except subprocess.TimeoutExpired:
            process.kill()


def print_html_to_pdf(page: Path, pdf: Path, workdir: Path) -> Path:
    """Print one HTML file to `pdf` with headless Chrome, sized by the page's own @page rule.

    Chrome 153 writes the PDF and then declines to exit, so we wait on the file reaching its
    %%EOF trailer rather than on the process. A throwaway profile keeps it clear of the
    user's running Chrome.
    """
    chrome = find_chrome()
    profile = workdir / "chrome-profile"
    process = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", f"--user-data-dir={profile}",
         "--no-first-run", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", page.as_uri()],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + config.RENDER_TIMEOUT
        while time.monotonic() < deadline:
            if pdf_is_complete(pdf):
                return pdf
            if process.poll() is not None:
                break
            time.sleep(config.POLL_INTERVAL)
    finally:
        _stop(process)

    if pdf_is_complete(pdf):
        return pdf
    errors = (process.stderr.read() or b"").decode(errors="replace").strip()
    detail = errors if len(errors) <= 1600 else errors[:1200] + "\n…\n" + errors[-400:]
    die(f"chrome produced no usable PDF: {detail or 'timed out'}")


def build_pdf(article, workdir: Path, stem: str) -> Path:
    page = workdir / "page.html"
    page.write_text(render_document(article, load_css("print.css")), encoding="utf-8")
    return print_html_to_pdf(page, workdir / f"{stem}.pdf", workdir)


def build_epub(article, url: str, workdir: Path, stem: str) -> Path:
    if not shutil.which("pandoc"):
        die("pandoc not found on PATH (brew install pandoc)")

    source = workdir / "article.html"
    source.write_text(article.html, encoding="utf-8")
    stylesheet = workdir / "epub.css"
    stylesheet.write_text(load_css("epub.css"), encoding="utf-8")
    epub = workdir / f"{stem}.epub"

    command = [
        "pandoc", str(source), "--from=html", "--to=epub3", f"--output={epub}",
        f"--css={stylesheet}", f"--metadata=title:{article.title}",
        f"--metadata=source:{url}", "--metadata=lang:en",
        "--toc", "--toc-depth=2", "--split-level=1",
    ]
    if article.author:
        command.append(f"--metadata=author:{article.author}")

    # cwd matters: localized images are referenced as media/imageN relative to workdir.
    result = subprocess.run(command, capture_output=True, text=True, cwd=workdir)
    if result.returncode != 0:
        die(f"pandoc failed: {result.stderr.strip() or result.returncode}")
    if not epub.is_file():
        die("pandoc reported success but produced no EPUB")
    return epub
