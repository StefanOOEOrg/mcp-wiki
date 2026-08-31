"""Process the drop-zone: move each queued file into the corpus and index it."""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

from . import config, index
from .config import TEXT_EXT

INBOX = "inbox"


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    for i in range(1, 1000):
        cand = dest.with_stem(f"{dest.stem}-{i}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"cannot find free name for {dest}")


def ingest_queue(db: sqlite3.Connection) -> dict:
    queue_dir = config.queue_dir()
    corpus_dir = config.corpus_dir()
    queue_dir.mkdir(parents=True, exist_ok=True)
    target_dir = corpus_dir / INBOX
    target_dir.mkdir(parents=True, exist_ok=True)
    counts = {"moved": 0, "indexed": 0, "unsupported": 0, "errors": 0}

    for src in sorted(queue_dir.iterdir()):
        if src.name.startswith(".") or not src.is_file():
            continue
        dest = _unique(target_dir / src.name)
        try:
            shutil.move(str(src), str(dest))
        except OSError as exc:
            print(f"  {src.name}: move failed: {exc}", file=sys.stderr)
            counts["errors"] += 1
            continue
        counts["moved"] += 1
        if dest.suffix.lower() not in TEXT_EXT:
            counts["unsupported"] += 1
            print(f"  {dest.name}: stored, not indexed (unsupported type)", file=sys.stderr)
            continue
        res = index.index_file(db, dest, corpus_dir)
        if res == "indexed":
            counts["indexed"] += 1
        elif res.startswith("error"):
            counts["errors"] += 1
            print(f"  {dest.name}: {res}", file=sys.stderr)
    return counts
