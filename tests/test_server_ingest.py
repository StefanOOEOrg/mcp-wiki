import asyncio
import inspect

import pytest


def _tools(srv):
    r = srv.mcp.list_tools()
    return list(asyncio.run(r) if inspect.iscoroutine(r) else r)


EXPECTED = {
    "wiki_search", "wiki_get", "wiki_answer", "wiki_stats", "wiki_add",
    "wiki_update", "wiki_remove", "wiki_reindex", "wiki_ingest_queue",
}


def test_all_tools_registered(wiki):
    names = {t.name for t in _tools(wiki.server)}
    assert EXPECTED <= names
    for t in _tools(wiki.server):
        assert t.description and len(t.description) > 15


def test_wiki_reindex_then_search_tool(wiki):
    out = wiki.server.wiki_reindex()
    assert out["documents"] == 3
    hits = wiki.server.wiki_search("Detroit Red Wings")
    assert any(h["path"] == "hockey.md" for h in hits)


def test_wiki_get(wiki):
    wiki.server.wiki_reindex()
    doc = wiki.server.wiki_get("notes/wien.md")
    assert doc["frontmatter"]["title"] == "Wien"
    assert "Leopoldstadt" in doc["text"]


def test_wiki_get_rejects_escape(wiki):
    with pytest.raises(ValueError):
        wiki.server.wiki_get("../../../etc/passwd")


def test_wiki_add_creates_and_indexes(wiki):
    wiki.server.wiki_reindex()
    res = wiki.server.wiki_add("Pandas are bears native to China.",
                               title="Panda", tags=["animals"])
    assert res["path"] == "inbox/panda.md"
    assert (wiki.root / "corpus" / "inbox" / "panda.md").is_file()
    hits = wiki.server.wiki_search("Pandas China bears")
    assert any(h["path"] == "inbox/panda.md" for h in hits)


def test_wiki_remove(wiki):
    wiki.server.wiki_reindex()
    wiki.server.wiki_remove("hockey.md")
    assert not (wiki.root / "corpus" / "hockey.md").exists()
    assert wiki.server.wiki_stats()["documents"] == 2


def test_wiki_update_keeps_frontmatter(wiki):
    wiki.server.wiki_reindex()
    wiki.server.wiki_update("notes/wien.md", "# Wien\n\nNeuer Text ohne Frontmatter.")
    doc = wiki.server.wiki_get("notes/wien.md")
    assert doc["frontmatter"]["title"] == "Wien"       # preserved
    assert "Neuer Text" in doc["text"]


def test_ingest_queue(wiki):
    wiki.server.wiki_reindex()
    (wiki.root / "queue" / "drop.md").write_text(
        "# Dropped note\n\nSomething about quantum entanglement.\n")
    counts = wiki.server.wiki_ingest_queue()
    assert counts["moved"] == 1 and counts["indexed"] == 1
    assert (wiki.root / "corpus" / "inbox" / "drop.md").is_file()
    assert not (wiki.root / "queue" / "drop.md").exists()
    hits = wiki.server.wiki_search("quantum entanglement")
    assert any("drop.md" in h["path"] for h in hits)


def test_ingest_queue_unsupported_type(wiki):
    wiki.server.wiki_reindex()
    (wiki.root / "queue" / "data.bin").write_bytes(b"\x00\x01\x02")
    counts = wiki.server.wiki_ingest_queue()
    assert counts["moved"] == 1 and counts["unsupported"] == 1 and counts["indexed"] == 0
