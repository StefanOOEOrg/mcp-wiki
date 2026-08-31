"""Parse a markdown document into retrieval chunks.

A chunk is a contiguous slice of one document under a heading path. Tables are
kept whole as their own chunk; prose is split at headings (H1-H3) and at a soft
character cap.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import CHUNK_MAX_CHARS

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


@dataclass
class Chunk:
    ord: int
    kind: str                       # "prose" | "table" | "caption"
    heading_path: list[str]
    text: str


@dataclass
class ImageRef:
    alt: str
    target: str
    heading_path: list[str]


@dataclass
class Document:
    path: str                       # relative to the corpus root, posix
    title: str
    section: str
    doctype: str
    tags: list[str]
    frontmatter: dict[str, Any]
    body: str
    chunks: list[Chunk] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            (self.title + "\0" + self.body).encode("utf-8")
        ).hexdigest()


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_-]+", "-", text)[:80] or "untitled"


def split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER.match(raw)
    if not m:
        return {}, raw
    try:
        data = yaml.safe_load(m.group(1)) or {}
        if not isinstance(data, dict):
            data = {}
    except yaml.YAMLError:
        data = {}
    return data, raw[m.end():]


def _chunk_body(body: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    heading_path: list[str] = []
    buf: list[str] = []
    lines = body.splitlines()
    i = 0
    order = 0

    def flush() -> None:
        nonlocal order
        text = "\n".join(buf).strip()
        buf.clear()
        if not text:
            return
        # soft-split overlong prose at blank lines
        if len(text) <= CHUNK_MAX_CHARS:
            pieces = [text]
        else:
            pieces, cur = [], ""
            for para in text.split("\n\n"):
                if cur and len(cur) + len(para) > CHUNK_MAX_CHARS:
                    pieces.append(cur.strip())
                    cur = para
                else:
                    cur = f"{cur}\n\n{para}" if cur else para
            if cur.strip():
                pieces.append(cur.strip())
        for p in pieces:
            chunks.append(Chunk(order, "prose", list(heading_path), p))
            order += 1

    while i < len(lines):
        line = lines[i]
        hm = _HEADING.match(line)
        if hm:
            flush()
            level = len(hm.group(1))
            title = hm.group(2).strip()
            if level <= 3:
                heading_path = heading_path[: level - 1] + [title]
            else:
                buf.append(line)
            i += 1
            continue
        if _TABLE_ROW.match(line):
            flush()
            tbl = []
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                tbl.append(lines[i])
                i += 1
            ctx = " › ".join(heading_path)
            body_txt = "\n".join(tbl)
            chunks.append(
                Chunk(order, "table",
                      list(heading_path),
                      (f"Table under {ctx}:\n{body_txt}" if ctx else body_txt))
            )
            order += 1
            continue
        buf.append(line)
        i += 1
    flush()
    return chunks


def _collect_images(body: str) -> list[ImageRef]:
    refs: list[ImageRef] = []
    heading_path: list[str] = []
    for line in body.splitlines():
        hm = _HEADING.match(line)
        if hm and len(hm.group(1)) <= 3:
            level = len(hm.group(1))
            heading_path = heading_path[: level - 1] + [hm.group(2).strip()]
            continue
        for alt, target in _IMAGE.findall(line):
            refs.append(ImageRef(alt.strip(), target.strip(), list(heading_path)))
    return refs


def parse(path: Path, corpus_root: Path) -> Document:
    raw = path.read_text(encoding="utf-8", errors="replace")
    fm, body = split_frontmatter(raw)

    rel = path.relative_to(corpus_root).as_posix()
    section = path.parent.relative_to(corpus_root).as_posix()
    section = "" if section == "." else section

    title = str(fm.get("title") or "").strip()
    if not title:
        for line in body.splitlines():
            hm = _HEADING.match(line)
            if hm:
                title = hm.group(2).strip()
                break
    if not title:
        title = path.stem.replace("-", " ").replace("_", " ")

    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in re.split(r"[,\s]+", tags) if t.strip()]
    tags = [str(t) for t in tags]

    doc = Document(
        path=rel,
        title=title,
        section=section,
        doctype=str(fm.get("type") or "note"),
        tags=tags,
        frontmatter=fm,
        body=body,
    )
    doc.chunks = _chunk_body(body)
    doc.images = _collect_images(body)
    return doc


def new_document_text(text: str, *, title: str | None, tags: list[str] | None,
                      source: str | None, doctype: str = "note") -> tuple[str, str]:
    """Return (filename, file_content) for a document added via wiki_add."""
    from datetime import date

    title = (title or text.strip().splitlines()[0][:80] or "note").strip()
    fm: dict[str, Any] = {"title": title, "type": doctype, "added": date.today().isoformat()}
    if tags:
        fm["tags"] = list(tags)
    if source:
        fm["source"] = source
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    body = text if text.lstrip().startswith("#") else f"# {title}\n\n{text}"
    return f"{_slugify(title)}.md", f"---\n{front}\n---\n\n{body.strip()}\n"
