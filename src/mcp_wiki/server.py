"""MCP server: search, read and write a local markdown knowledge base."""

from __future__ import annotations

from pathlib import Path

from mcp.server import MCPServer

from . import config, index, retrieve, store
from .doc import new_document_text, split_frontmatter
from .ingest import ingest_queue

mcp = MCPServer(
    "mcp-wiki",
    version="0.1.0",
    instructions=(
        "A local RAG knowledge base over a folder of markdown documents. Use "
        "wiki_search / wiki_answer to retrieve, wiki_get to read a whole "
        "document. Only call wiki_add / wiki_update / wiki_remove when the user "
        "explicitly asks to store or change something. Paths are relative to the "
        "corpus root."
    ),
)


def _safe_path(path: str) -> Path:
    root = config.corpus_dir().resolve()
    p = (root / path).resolve()
    if not p.is_relative_to(root):
        raise ValueError(f"path escapes the corpus: {path!r}")
    return p


# ---- read ----------------------------------------------------------

@mcp.tool()
def wiki_search(query: str, k: int = 8, section: str | None = None,
                tags: list[str] | None = None) -> list[dict]:
    """Hybrid semantic + keyword search. Returns matching documents with score,
    the sections that matched and a snippet each. Optional filters: ``section``
    (a corpus sub-folder) and ``tags``."""
    db = store.connect()
    try:
        return retrieve.search(db, query, k=k, section=section, tags=tags)
    finally:
        db.close()


@mcp.tool()
def wiki_get(path: str) -> dict:
    """Return the full content and frontmatter of one document."""
    fp = _safe_path(path)
    if not fp.is_file():
        raise ValueError(f"no such document: {path}")
    raw = fp.read_text(encoding="utf-8", errors="replace")
    fm, body = split_frontmatter(raw)
    return {"path": path, "frontmatter": fm, "text": body}


@mcp.tool()
def wiki_answer(query: str, k: int = 6) -> dict:
    """Retrieve relevant excerpts and answer the question from them, with
    citations. Returns {answer, sources}."""
    db = store.connect()
    try:
        return retrieve.answer(db, query, k=k)
    finally:
        db.close()


@mcp.tool()
def wiki_stats() -> dict:
    """Index size: number of documents, chunks and cached image captions."""
    db = store.connect()
    try:
        return store.stats(db)
    finally:
        db.close()


# ---- write (explicit instruction only) ----------------------------

@mcp.tool()
def wiki_add(text: str, title: str | None = None, tags: list[str] | None = None,
            section: str = "inbox", source: str | None = None) -> dict:
    """Create a new document in the corpus and index it. ``section`` is a
    sub-folder (created if needed). Call this only when the user asked to save
    something."""
    fname, content = new_document_text(text, title=title, tags=tags, source=source)
    dest_dir = _safe_path(section) if section else config.corpus_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fname
    n = 1
    while dest.exists():
        dest = dest_dir / f"{Path(fname).stem}-{n}.md"
        n += 1
    dest.write_text(content, encoding="utf-8")
    db = store.connect()
    try:
        res = index.index_file(db, dest)
    finally:
        db.close()
    rel = dest.relative_to(config.corpus_dir()).as_posix()
    return {"path": rel, "status": res}


@mcp.tool()
def wiki_update(path: str, text: str) -> dict:
    """Replace a document's content. If ``text`` has no frontmatter the existing
    frontmatter is kept."""
    fp = _safe_path(path)
    if not fp.is_file():
        raise ValueError(f"no such document: {path}")
    fm_new, _ = split_frontmatter(text)
    if not fm_new:
        old_fm_raw = fp.read_text(encoding="utf-8", errors="replace")
        fm_old, _ = split_frontmatter(old_fm_raw)
        if fm_old:
            import yaml
            front = yaml.safe_dump(fm_old, allow_unicode=True, sort_keys=False).strip()
            text = f"---\n{front}\n---\n\n{text.lstrip()}"
    fp.write_text(text, encoding="utf-8")
    db = store.connect()
    try:
        res = index.index_file(db, fp, force=True)
    finally:
        db.close()
    return {"path": path, "status": res}


@mcp.tool()
def wiki_remove(path: str) -> dict:
    """Delete a document from the corpus and the index."""
    fp = _safe_path(path)
    if not fp.is_file():
        raise ValueError(f"no such document: {path}")
    fp.unlink()
    db = store.connect()
    try:
        store.remove_document(db, path)
    finally:
        db.close()
    return {"path": path, "status": "removed"}


@mcp.tool()
def wiki_reindex(full: bool = False) -> dict:
    """Rebuild the index from the corpus folder. ``full=True`` re-embeds every
    document; otherwise only changed files are touched."""
    db = store.connect()
    try:
        counts = index.reindex(db, full=full)
        counts.update(store.stats(db))
        return counts
    finally:
        db.close()


@mcp.tool()
def wiki_ingest_queue() -> dict:
    """Process the drop-zone (``queue/``): move each file into the corpus and
    index it. Normally run automatically by a watcher; exposed for manual use."""
    db = store.connect()
    try:
        return ingest_queue(db)
    finally:
        db.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
