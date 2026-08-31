"""Hybrid retrieval: dense (sqlite-vec) + lexical (FTS5 BM25), merged per chunk
with Reciprocal Rank Fusion, then grouped to documents.

Document score = the best matching chunk's fused score, with a small bonus for
having several independent hits. Using the *best* chunk (not a sum) keeps a long
reference document from drowning a short, exactly-relevant note just because it
has hundreds of chunks in the candidate pool.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any

from . import llm, store

RRF_K = 60
POOL = 60
MULTI_HIT_BONUS = 0.12          # per extra matched chunk, capped
MULTI_HIT_CAP = 3


def _rrf(*ranked_lists: list[int]) -> dict[int, float]:
    scores: dict[int, float] = {}
    for lst in ranked_lists:
        for rank, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def search(db: sqlite3.Connection, query: str, *, k: int = 8,
           pool: int = POOL, section: str | None = None,
           tags: list[str] | None = None) -> list[dict[str, Any]]:
    qvec = llm.embed([query])[0]
    dense = [cid for cid, _ in store.search_dense(db, qvec, pool)]
    lexical = [cid for cid, _ in store.search_fts(db, query, pool)]
    fused = _rrf(dense, lexical)
    if not fused:
        return []

    rows = store.chunk_rows(db, list(fused))
    by_doc: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
    for cid, score in fused.items():
        row = rows.get(cid)
        if not row:
            continue
        if section is not None and row["section"] != section:
            continue
        if tags and not (set(tags) & set(row["tags"])):
            continue
        by_doc[row["doc_path"]].append((score, row))

    results: list[dict[str, Any]] = []
    for path, matches in by_doc.items():
        matches.sort(key=lambda m: -m[0])
        best = matches[0][0]
        bonus = 1.0 + MULTI_HIT_BONUS * min(len(matches) - 1, MULTI_HIT_CAP)
        row0 = matches[0][1]
        results.append({
            "path": path,
            "title": row0["title"],
            "section": row0["section"],
            "tags": row0["tags"],
            "score": round(best * bonus, 4),
            "hits": [
                {"kind": r["kind"], "heading_path": r["heading_path"],
                 "snippet": _snippet(r["text"])}
                for _, r in matches[:3]
            ],
        })
    results.sort(key=lambda d: -d["score"])
    return results[:k]


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
