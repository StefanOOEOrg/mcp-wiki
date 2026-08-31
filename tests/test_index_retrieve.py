from mcp_wiki import store


def test_full_index_and_stats(wiki):
    db = store.connect()
    counts = wiki.index.reindex(db)
    assert counts["indexed"] == 3
    assert counts["errors"] == 0
    s = store.stats(db)
    assert s["documents"] == 3
    assert s["chunks"] >= 5           # prose + table + caption
    assert s["captions"] == 1         # diagram.png captioned once
    db.close()


def test_dot_dirs_are_skipped(wiki):
    (wiki.root / "corpus" / ".obsidian").mkdir()
    (wiki.root / "corpus" / ".obsidian" / "notes.md").write_text("# hidden\n\nsecret vault config")
    db = store.connect()
    counts = wiki.index.reindex(db)
    assert counts["indexed"] == 3          # still only the 3 real docs
    assert store.stats(db)["documents"] == 3
    assert ".obsidian/notes.md" not in {d["path"] for d in store.list_documents(db)}
    db.close()


def test_incremental_skip(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    counts = wiki.index.reindex(db)
    assert counts["indexed"] == 0
    assert counts["skipped"] == 3
    db.close()


def test_reindex_after_edit(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    p = wiki.root / "corpus" / "hockey.md"
    p.write_text(p.read_text() + "\n\nDavid Reinbacher plays defense for Montreal.\n")
    counts = wiki.index.reindex(db)
    assert counts["indexed"] == 1 and counts["skipped"] == 2
    db.close()


def test_prune_deleted_file(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    (wiki.root / "corpus" / "hockey.md").unlink()
    counts = wiki.index.reindex(db)
    assert counts["pruned"] == 1
    assert store.stats(db)["documents"] == 2
    db.close()


def test_search_finds_by_keyword(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    hits = wiki.retrieve.search(db, "Leopoldstadt Einwohner", k=5)
    assert hits and hits[0]["path"] == "notes/wien.md"
    # the table chunk should be among the matched snippets
    assert any(h["kind"] == "table" for h in hits[0]["hits"])
    db.close()


def test_search_finds_image_via_caption(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    hits = wiki.retrieve.search(db, "retrieval diagram", k=5)
    paths = [h["path"] for h in hits]
    assert "concepts/rag.md" in paths
    db.close()


def test_search_section_filter(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    hits = wiki.retrieve.search(db, "Wien Kasper Rossi", k=5, section="notes")
    assert all(h["section"] == "notes" for h in hits)
    db.close()


def test_search_tag_filter(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    hits = wiki.retrieve.search(db, "retrieval hybrid vienna", k=5, tags=["ai"])
    assert hits and all("ai" in h["tags"] for h in hits)
    db.close()


def test_long_doc_does_not_bury_short_exact_match(wiki):
    """A short note whose one chunk names the term must outrank a huge
    document that merely mentions it in passing among hundreds of chunks."""
    big = wiki.root / "corpus" / "big.md"
    body = "# Big reference\n\n" + "\n\n".join(
        f"## Section {i}\n\nGeneric filler about logistics and dispatching item {i}."
        for i in range(200)
    ) + "\n\n## Aside\n\nSomeone once mentioned zeppelins here.\n"
    big.write_text(body)
    (wiki.root / "corpus" / "zeppelin.md").write_text(
        "# Zeppelin\n\nA zeppelin is a rigid airship. Zeppelins fly using lifting gas.\n")
    db = store.connect()
    wiki.index.reindex(db)
    hits = wiki.retrieve.search(db, "zeppelin airship lifting gas", k=5)
    assert hits[0]["path"] == "zeppelin.md"
    db.close()


def test_answer_shape(wiki):
    db = store.connect()
    wiki.index.reindex(db)
    res = wiki.retrieve.answer(db, "who plays for Detroit?")
    assert res["answer"] == "STUB ANSWER [1]"
    assert res["sources"] and res["sources"][0]["path"]
    db.close()
