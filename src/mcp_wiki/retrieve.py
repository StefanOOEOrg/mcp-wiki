"""Hybrid retrieval: dense (sqlite-vec) + lexical (FTS5 BM25), merged with
Reciprocal Rank Fusion, then grouped by document."""

from __future__ import annotations

import sqlite3
from typing import Any

from . import llm, store

RRF_K = 60


def _rrf(*ranked_lists: list[int]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for lst in ranked_lists:
        for rank, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def search(db: sqlite3.Connection, query: str, *, k: int = 8,
           pool: int = 40, section: str | None = None,
           tags: list[str] | None = None) -> list[dict[str, Any]]:
    qvec = llm.embed([query])[0]
    dense = [cid for cid, _ in store.search_dense(db, qvec, pool)]
    lexical = [cid for cid, _ in store.search_fts(db, query, pool)]
    fused = _rrf(dense, lexical)
    if not fused:
        return []

    rows = store.chunk_rows(db, list(fused))
    per_doc: dict[str, dict[str, Any]] = {}
    for cid, score in sorted(fused.items(), key=lambda kv: -kv[1]):
        row = rows.get(cid)
        if not row:
            continue
        if section is not None and row["section"] != section:
            continue
        if tags and not (set(tags) & set(row["tags"])):
            continue
        doc = per_doc.setdefault(row["doc_path"], {
            "path": row["doc_path"], "title": row["title"],
            "section": row["section"], "tags": row["tags"],
            "score": 0.0, "hits": [],
        })
        doc["score"] += score
        if len(doc["hits"]) < 3:
            doc["hits"].append({
                "kind": row["kind"],
                "heading_path": row["heading_path"],
                "snippet": _snippet(row["text"]),
            })
    ranked = sorted(per_doc.values(), key=lambda d: -d["score"])
    return ranked[:k]


def _snippet(text: str, limit: int = 320) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def answer(db: sqlite3.Connection, query: str, *, k: int = 6) -> dict[str, Any]:
    hits = search(db, query, k=k)
    if not hits:
        return {"answer": "No matching documents in the wiki.", "sources": []}
    context = "\n\n".join(
        f"[{i + 1}] {h['title']} ({h['path']})\n" +
        "\n".join(s["snippet"] for s in h["hits"])
        for i, h in enumerate(hits)
    )
    reply = llm.chat([
        {"role": "system", "content":
            "Answer the question using only the numbered wiki excerpts. Cite "
            "sources as [n]. If the excerpts do not contain the answer, say so."},
        {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {query}"},
    ])
    return {
        "answer": reply,
        "sources": [{"n": i + 1, "path": h["path"], "title": h["title"]}
                    for i, h in enumerate(hits)],
    }
