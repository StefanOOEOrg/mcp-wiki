"""Resolve image references and turn them into caption chunks (cached by the
image's content hash so re-indexing is cheap)."""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import sqlite3
from pathlib import Path

from . import config, llm, store
from .doc import Document, ImageRef

_MAX_BYTES = 8 * 1024 * 1024


def _resolve(ref: ImageRef, doc_path: str) -> Path | None:
    target = ref.target.split("#", 1)[0].split("?", 1)[0]
    if target.startswith(("http://", "https://", "data:")):
        return None
    doc_dir = (config.corpus_dir() / doc_path).parent
    for cand in (doc_dir / target, config.corpus_dir() / target,
                 config.attachments_dir() / Path(target).name, Path(target).expanduser()):
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            continue
    return None


def caption_chunks(db: sqlite3.Connection, doc: Document) -> list[str]:
    if not config.captions_enabled() or not doc.images:
        return []
    out: list[str] = []
    for ref in doc.images:
        fp = _resolve(ref, doc.path)
        if not fp:
            if ref.alt:
                out.append(f"Image ({ref.target}): {ref.alt}")
            continue
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        if len(raw) > _MAX_BYTES:
            continue
        sha = hashlib.sha256(raw).hexdigest()
        cap = store.get_caption(db, sha)
        if cap is None:
            mime = mimetypes.guess_type(fp.name)[0] or "image/png"
            uri = f"data:{mime};base64," + base64.b64encode(raw).decode()
            try:
                cap = llm.caption_image(uri, ref.alt)
            except llm.LLMError:
                cap = ""
            store.put_caption(db, sha, ref.alt, cap)
        ctx = " › ".join(ref.heading_path)
        parts = [p for p in (f"Image: {ref.alt}" if ref.alt else "Image",
                             f"in {ctx}" if ctx else "", cap) if p]
        out.append(". ".join(parts))
    return out
