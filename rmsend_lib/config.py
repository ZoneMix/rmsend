"""Constants and environment overrides for rmsend. No secrets live here."""

from __future__ import annotations

import os
import re
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent

HOST = os.environ.get("RMSEND_HOST", "10.11.99.1")
SSH_HOST = os.environ.get("RMSEND_SSH_HOST", "remarkable")
ASSET_DIR = Path(os.environ.get("RMSEND_ASSETS") or _PACKAGE_ROOT / "assets").expanduser()
XOCHITL_DIR = os.environ.get(
    "RMSEND_XOCHITL_DIR", "/home/root/.local/share/remarkable/xochitl"
)
WEB_PORT = 80
PROBE_TIMEOUT = 4
FETCH_TIMEOUT = 30
UPLOAD_TIMEOUT = 180
SSH_TIMEOUT = 300
RENDER_TIMEOUT = 180
POLL_INTERVAL = 0.4
MIN_PDF_BYTES = 1024
PDF_TRAILER_WINDOW = 2048
IMAGE_WORKERS = 6
PASSTHROUGH_SUFFIXES = frozenset({".pdf", ".epub"})
HTML_SUFFIXES = frozenset({".html", ".htm"})
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
# Keep Unicode letters and digits; drop only what filesystems or the tablet choke on.
FILENAME_SAFE = re.compile(r"[^\w .,'()&-]+", re.UNICODE)
MAX_STEM = 120
DEFAULT_MARGINS = 180
TRASH_PARENT = "trash"
RETENTION_MODES = ("rm", "trash")

ENDNOTE_MARKER = re.compile(r"^\[(\d+)\]")
FOOTNOTE_REF = re.compile(r"^\[?(\d+)\]?$")
LEGACY_FOOTNOTE_HREF = re.compile(r"#_ftn", re.I)
ATTRIBUTION = re.compile(r"^\s*[—–]")
CAPTION_HINT = re.compile(r"creativecommons\.org|^\s*(Photo|Image|Credit|Source|Figure)", re.I)
MAX_CAPTION_CHARS = 220
MAX_ATTRIBUTION_CHARS = 200
MAX_QUOTE_CHARS = 400
BOILERPLATE = (
    re.compile(r"view entire message", re.I),
    re.compile(r"^\s*(Share|Leave a comment|Subscribe now|Share this post)\s*\.?\s*$", re.I),
    re.compile(r"Thanks for reading.{0,80}\bsubscribe\b", re.I),
)

DOCUMENT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<header class="masthead">
<h1>{title}</h1>
{subtitle}
{byline}
{dateline}
</header>
<article>
{body}
</article>
</body>
</html>
"""
