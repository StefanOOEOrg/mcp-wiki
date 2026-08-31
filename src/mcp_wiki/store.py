"""SQLite storage: document metadata, chunks, a sqlite-vec vector index, an FTS5
lexical index, and an image-caption cache."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import sqlite_vec

from .config import EMBED_DIM, db_path
from .doc import Document

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS documents (
    path        TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    title       TEXT,
    section     TEXT,
    doctype     TEXT,
    tags        TEXT,          -- json array
    indexed_at  REAL
);
CREATE TABLE IF NOT EXISTS chunks (
    id           INTEGER PRIMARY KEY,
    doc_path     TEXT NOT NULL REFERENCES documents(path) ON DELETE CASCADE,
    ord          INTEGER,
    kind         TEXT,
    heading_path TEXT,
    text         TEXT
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_path);
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding FLOAT[{EMBED_DIM}]
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(text);
CREATE TABLE IF NOT EXISTS image_captions (
    sha        TEXT PRIMARY KEY,
    alt        TEXT,
    caption    TEXT,
    created_at REAL
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(p)
    db.row_factory = sqlite3.Row
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(_SCHEMA)
    return db


# ---- documents -------------------------------------------------------

def stored_hash(db: sqlite3.Connection, path: str) -> str | None:
    row = db.execute("SELECT hash FROM documents WHERE path = ?", (path,)).fetchone()
    return row["hash"] if row else None


def all_paths(db: sqlite3.Connection) -> set[str]:
    return {r["path"] for r in db.execute("SELECT path FROM documents")}


def remove_document(db: sqlite3.Connection, path: str) -> None:
    ids = [r["id"] for r in db.execute(
        "SELECT id FROM chunks WHERE doc_path = ?", (path,))]
    for cid in ids:
        db.execute("DELETE FROM vec_chunks WHERE chunk_id = ?", (cid,))
        db.execute("DELETE FROM fts_chunks WHERE rowid = ?", (cid,))
    db.execute("DELETE FROM documents WHERE path = ?", (path,))  # cascades chunks
    db.commit()


def upsert_document(db: sqlite3.Connection, doc: Document,
                    texts: list[str], embeddings: list[list[float]]) -> int:
    """Replace all rows for ``doc.path``. ``texts``/``embeddings`` are aligned
    and already include any caption chunks appended after the body chunks."""
    remove_document(db, doc.path)
    db.execute(
        "INSERT INTO documents(path, hash, title, section, doctype, tags, indexed_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (doc.path, doc.content_hash, doc.title, doc.section, doc.doctype,
         json.dumps(doc.tags), time.time()),
    )
    extra = len(texts) - len(doc.chunks)
    kinds = [c.kind for c in doc.chunks] + ["caption"] * extra
    heads = [json.dumps(c.heading_path) for c in doc.chunks] + ["[]"] * extra
    rows = zip(texts, embeddings, kinds, heads, strict=True)
    for ordi, (text, emb, kind, head) in enumerate(rows):
        cur = db.execute(
            "INSERT INTO chunks(doc_path, ord, kind, heading_path, text) VALUES (?,?,?,?,?)",
            (doc.path, ordi, kind, head, text),
        )
        cid = cur.lastrowid
        db.execute("INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
                   (cid, sqlite_vec.serialize_float32(emb)))
        db.execute("INSERT INTO fts_chunks(rowid, text) VALUES (?, ?)", (cid, text))
    db.commit()
    return len(texts)


def document(db: sqlite3.Connection, path: str) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM documents WHERE path = ?", (path,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["tags"] = json.loads(d["tags"] or "[]")
    return d


def list_documents(db: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    q = "SELECT path, title, section, doctype, tags FROM documents ORDER BY path"
    for row in db.execute(q):
        d = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        out.append(d)
    return out


def chunks_for(db: sqlite3.Connection, path: str) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute(
        "SELECT ord, kind, heading_path, text FROM chunks WHERE doc_path = ? ORDER BY ord",
        (path,))]


# ---- search ---------------------------------------------------------

def _fts_query(text: str) -> str:
    toks = re.findall(r"\w+", text.lower())
    return " OR ".join(f'"{t}"' for t in toks) if toks else '""'


def search_dense(db: sqlite3.Connection, qvec: list[float], k: int) -> list[tuple[int, float]]:
    rows = db.execute(
        "SELECT chunk_id, distance FROM vec_chunks "
        "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (sqlite_vec.serialize_float32(qvec), k),
    ).fetchall()
    return [(r["chunk_id"], r["distance"]) for r in rows]


def search_fts(db: sqlite3.Connection, query: str, k: int) -> list[tuple[int, float]]:
    try:
        rows = db.execute(
            "SELECT rowid, bm25(fts_chunks) AS rank FROM fts_chunks "
            "WHERE fts_chunks MATCH ? ORDER BY rank LIMIT ?",
            (_fts_query(query), k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r["rowid"], r["rank"]) for r in rows]


def chunk_rows(db: sqlite3.Connection, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    q = ("SELECT c.id, c.doc_path, c.kind, c.heading_path, c.text, "
         "d.title, d.section, d.tags "
         "FROM chunks c JOIN documents d ON d.path = c.doc_path "
         f"WHERE c.id IN ({','.join('?' * len(ids))})")
    out = {}
    for r in db.execute(q, ids):
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        d["heading_path"] = json.loads(d["heading_path"] or "[]")
        out[r["id"]] = d
    return out


# ---- caption cache -------------------------------------------------

def get_caption(db: sqlite3.Connection, sha: str) -> str | None:
    row = db.execute("SELECT caption FROM image_captions WHERE sha = ?", (sha,)).fetchone()
    return row["caption"] if row else None


def put_caption(db: sqlite3.Connection, sha: str, alt: str, caption: str) -> None:
    db.execute(
        "INSERT OR REPLACE INTO image_captions(sha, alt, caption, created_at) VALUES (?,?,?,?)",
        (sha, alt, caption, time.time()),
    )
    db.commit()


def stats(db: sqlite3.Connection) -> dict[str, int]:
    return {
        "documents": db.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunks": db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "captions": db.execute("SELECT COUNT(*) FROM image_captions").fetchone()[0],
    }
