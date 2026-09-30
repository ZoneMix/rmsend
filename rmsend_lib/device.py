"""Getting documents onto the tablet: USB web upload, or SSH with hand-built sidecars.

Standard library only. The SSH path installs N documents in one tar stream, can file them
into a named folder (an existing CollectionType), prune older same-titled documents to a
retention count, and restarts xochitl exactly once. The device shell is BusyBox: no curl,
no python, `head -n 1` not `head -1`.
"""

from __future__ import annotations

import json
import shlex
import socket
import subprocess
import sys
import tarfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from rmsend_lib import config


def die(message: str) -> NoReturn:
    print(f"rmsend: {message}", file=sys.stderr)
    raise SystemExit(1)


@dataclass(frozen=True)
class RemoteDoc:
    id: str
    visible_name: str
    parent: str
    doc_type: str
    last_modified: int
    deleted: bool


@dataclass(frozen=True)
class Outgoing:
    document: Path
    title: str


# --- probes ---------------------------------------------------------------


def web_interface_is_up() -> bool:
    try:
        with socket.create_connection((config.HOST, config.WEB_PORT), timeout=config.PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def _ssh(remote: str, *, stdin=None, timeout: int = config.SSH_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={config.PROBE_TIMEOUT}",
         config.SSH_HOST, remote],
        stdin=stdin, capture_output=True, text=stdin is None, timeout=timeout,
    )


def ssh_is_up() -> tuple[bool, str]:
    """(reachable, stderr tail) — the tail is what tells a sleeping tablet from a bad key."""
    try:
        probe = _ssh("true", timeout=config.PROBE_TIMEOUT * 3)
    except subprocess.TimeoutExpired:
        return False, "ssh probe timed out"
    return probe.returncode == 0, (probe.stderr or "").strip()[-300:]


# --- web transport ----------------------------------------------------------


def send_over_web(document: Path) -> None:
    import requests  # only the web transport needs it; keep device.py importable without it

    try:
        with document.open("rb") as handle:
            response = requests.post(
                f"http://{config.HOST}/upload",
                files={"file": (document.name, handle, "application/octet-stream")},
                timeout=config.UPLOAD_TIMEOUT,
            )
        response.raise_for_status()
    except requests.RequestException as exc:
        die(f"web upload failed: {exc}")
    print(f"sent over USB web interface: {document.name}")


# --- sidecars ---------------------------------------------------------------


def build_metadata(title: str, parent: str = "", doc_type: str = "DocumentType") -> str:
    now = str(int(time.time() * 1000))
    return json.dumps(
        {
            "createdTime": now,
            "deleted": False,
            "lastModified": now,
            "lastOpened": "0",
            "lastOpenedPage": 0,
            "metadatamodified": False,
            "modified": False,
            "new": False,
            "parent": parent,
            "pinned": False,
            "source": "",
            "synced": False,
            "type": doc_type,
            "version": 1,
            "visibleName": title,
        },
        indent=4,
    )


def build_content(title: str, file_type: str, size: int) -> str:
    """Minimal .content matching this firmware's schema. xochitl paginates on open."""
    return json.dumps(
        {
            "coverPageNumber": -1 if file_type == "epub" else 0,
            "documentMetadata": {"title": title},
            "dummyDocument": False,
            "extraMetadata": {},
            "fileType": file_type,
            "fontName": "",
            "formatVersion": 1,
            "lineHeight": -1,
            "margins": config.DEFAULT_MARGINS,
            "orientation": "portrait",
            "pageCount": 0,
            "pageTags": [],
            "pages": [],
            "redirectionPageMap": [],
            "sizeInBytes": str(size),
            "tags": [],
            "textAlignment": "justify",
            "textScale": 1,
        },
        indent=4,
    )


def build_folder_sidecars(name: str, folder_id: str) -> dict[str, str]:
    """A CollectionType entry = the same .metadata shape plus an empty .content."""
    return {f"{folder_id}.metadata": build_metadata(name, "", "CollectionType"),
            f"{folder_id}.content": "{}\n"}


def build_bundle(outgoing: tuple[Outgoing, ...], parent: str, workdir: Path,
                 new_folder: tuple[str, str] | None = None) -> Path:
    """Tar the three files xochitl needs per document, each under a fresh UUID. With
    `new_folder=(name, id)` the folder's own sidecars ride in the same tar first."""
    bundle = workdir / "bundle.tar"
    with tarfile.open(bundle, "w") as archive:
        if new_folder:
            for name, payload in build_folder_sidecars(*new_folder).items():
                staged = workdir / name
                staged.write_text(payload, encoding="utf-8")
                archive.add(staged, arcname=name)
        for item in outgoing:
            doc_id = str(uuid.uuid4())
            file_type = item.document.suffix.lower().lstrip(".")
            archive.add(item.document, arcname=f"{doc_id}.{file_type}")
            sidecars = {
                f"{doc_id}.metadata": build_metadata(item.title, parent),
                f"{doc_id}.content": build_content(item.title, file_type, item.document.stat().st_size),
            }
            for name, payload in sidecars.items():
                staged = workdir / name
                staged.write_text(payload, encoding="utf-8")
                archive.add(staged, arcname=name)
    return bundle


# --- library listing + retention --------------------------------------------

_LIST_COMMAND = (
    "cd {dir} && for f in *.metadata; do [ -f \"$f\" ] || continue; "
    "printf '%s\\t' \"${{f%.metadata}}\"; tr -d '\\n' < \"$f\"; printf '\\n'; done"
)


def parse_listing(text: str) -> tuple[RemoteDoc, ...]:
    docs = []
    for line in text.splitlines():
        doc_id, _, raw = line.partition("\t")
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            continue  # a torn or foreign file is not ours to reason about
        docs.append(RemoteDoc(
            id=doc_id,
            visible_name=str(meta.get("visibleName", "")),
            parent=str(meta.get("parent", "")),
            doc_type=str(meta.get("type", "")),
            last_modified=int(str(meta.get("lastModified", "0")) or 0),
            deleted=bool(meta.get("deleted", False)),
        ))
    return tuple(docs)


def list_documents() -> tuple[RemoteDoc, ...]:
    result = _ssh(_LIST_COMMAND.format(dir=shlex.quote(config.XOCHITL_DIR)))
    if result.returncode != 0:
        die(f"could not list the library: {result.stderr.strip() or result.returncode}")
    return parse_listing(result.stdout)


def find_folder(docs: tuple[RemoteDoc, ...], name: str) -> str | None:
    for doc in docs:
        if doc.doc_type == "CollectionType" and doc.visible_name == name and not doc.deleted:
            return doc.id
    return None


def select_prunable(docs: tuple[RemoteDoc, ...], folder_id: str, keep: int,
                    title_prefix: str) -> tuple[str, ...]:
    """Ids of the oldest same-titled documents in the folder beyond `keep`. Double-guarded:
    only DocumentType entries whose parent is the folder AND whose name starts with the prefix."""
    ours = sorted(
        (d for d in docs if d.parent == folder_id and d.doc_type == "DocumentType"
         and not d.deleted and d.visible_name.startswith(title_prefix)),
        key=lambda d: d.last_modified, reverse=True,
    )
    return tuple(d.id for d in ours[max(keep, 0):])


def _prune_command(prune_ids: tuple[str, ...], retention: str) -> str:
    if not prune_ids:
        return ""
    quoted = " ".join(shlex.quote(i) for i in prune_ids)
    if retention == "rm":
        return f' && for i in {quoted}; do rm -rf "$i" "$i".*; done'
    stamp = str(int(time.time() * 1000))
    return (f' && for i in {quoted}; do sed -i \'s/"parent": "[^"]*"/"parent": "{config.TRASH_PARENT}"/;'
            f' s/"lastModified": "[^"]*"/"lastModified": "{stamp}"/\' "$i.metadata"; done')


def send_over_ssh(outgoing: tuple[Outgoing, ...], workdir: Path, *, parent: str = "",
                  prune_ids: tuple[str, ...] = (), retention: str = "rm",
                  restart: bool = True, new_folder: tuple[str, str] | None = None) -> None:
    bundle = build_bundle(outgoing, parent, workdir, new_folder)
    remote = f"cd {shlex.quote(config.XOCHITL_DIR)} && tar -xf -" + _prune_command(prune_ids, retention)
    if restart:
        remote += " && systemctl restart xochitl"

    with bundle.open("rb") as handle:
        result = _ssh(remote, stdin=handle)
    if result.returncode != 0:
        detail = (result.stderr or b"").decode(errors="replace").strip()
        die(f"ssh transfer failed: {detail or result.returncode}")

    names = ", ".join(item.document.name for item in outgoing)
    print(f"sent over SSH: {names}")
    if new_folder:
        print(f"created folder: {new_folder[0]}")
    if prune_ids:
        verb = "removed" if retention == "rm" else "moved to trash"
        print(f"{verb} {len(prune_ids)} older document(s)")
    if restart:
        print("restarted xochitl; the library will redraw in a few seconds")
    else:
        print("skipped restart: it will not appear until xochitl restarts")
