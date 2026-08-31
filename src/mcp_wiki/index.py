"""Walk the corpus and (re)build the index, incrementally by content hash."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from . import config, images, llm, store
from . import doc as docmod
from .config import TEXT_EXT


def _iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_EXT and not p.name.startswith("."):
            yield p


def index_file(db: sqlite3.Connection, path: Path, corpus_root: Path | None = None,
               *, force: bool = False) -> str:
    """Return 'indexed' | 'skipped' | 'error:<msg>'."""
    corpus_root = Path(corpus_root or config.corpus_dir()).resolve()
    try:
        parsed = docmod.parse(Path(path).resolve(), corpus_root)
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop a run
        return f"error:{type(exc).__name__}: {exc}"
    if not force and store.stored_hash(db, parsed.path) == parsed.content_hash:
        return "skipped"

    texts = [c.text for c in parsed.chunks]
    texts += images.caption_chunks(db, parsed)
    if not texts:
        texts = [parsed.title]
    try:
        vectors = llm.embed(texts)
    except llm.LLMError as exc:
        return f"error:embed: {exc}"
    store.upsert_document(db, parsed, texts, vectors)
    return "indexed"


def reindex(db: sqlite3.Connection, corpus_root: Path | str | None = None,
            *, full: bool = False, prune: bool = True, verbose: bool = False) -> dict:
    corpus_root = Path(corpus_root or config.corpus_dir()).resolve()
    counts = {"indexed": 0, "skipped": 0, "errors": 0, "pruned": 0}
    seen: set[str] = set()
    for fp in _iter_files(corpus_root):
        rel = fp.relative_to(corpus_root).as_posix()
        seen.add(rel)
        res = index_file(db, fp, corpus_root, force=full)
        if res == "indexed":
            counts["indexed"] += 1
        elif res == "skipped":
            counts["skipped"] += 1
        else:
            counts["errors"] += 1
            print(f"  {rel}: {res}", file=sys.stderr)
        if verbose:
            print(f"  {rel}: {res}", file=sys.stderr)
    if prune:
        for gone in store.all_paths(db) - seen:
            store.remove_document(db, gone)
            counts["pruned"] += 1
    return counts
