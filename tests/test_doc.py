from pathlib import Path

from mcp_wiki.doc import new_document_text, parse, split_frontmatter

CORPUS = Path(__file__).parent / "fixtures" / "corpus"


def test_split_frontmatter():
    fm, body = split_frontmatter("---\ntitle: X\ntags: [a, b]\n---\n\nhello")
    assert fm == {"title": "X", "tags": ["a", "b"]}
    assert body.strip() == "hello"
    fm, body = split_frontmatter("no frontmatter here")
    assert fm == {} and body == "no frontmatter here"


def test_parse_metadata_and_section():
    d = parse(CORPUS / "notes" / "wien.md", CORPUS)
    assert d.path == "notes/wien.md"
    assert d.section == "notes"
    assert d.title == "Wien"
    assert d.doctype == "place"
    assert "austria" in d.tags


def test_parse_title_from_heading_when_no_frontmatter():
    d = parse(CORPUS / "hockey.md", CORPUS)
    assert d.title == "Austrian NHL players"
    assert d.section == ""


def test_table_is_one_chunk():
    d = parse(CORPUS / "notes" / "wien.md", CORPUS)
    tables = [c for c in d.chunks if c.kind == "table"]
    assert len(tables) == 1
    assert "Leopoldstadt" in tables[0].text and "Innere Stadt" in tables[0].text
    assert tables[0].heading_path == ["Wien", "Bezirke"]


def test_chunks_split_on_headings():
    d = parse(CORPUS / "notes" / "wien.md", CORPUS)
    heads = {tuple(c.heading_path) for c in d.chunks}
    assert ("Wien", "Klima") in heads


def test_image_refs_collected():
    d = parse(CORPUS / "concepts" / "rag.md", CORPUS)
    assert len(d.images) == 1
    assert d.images[0].target.endswith("diagram.png")
    assert d.images[0].heading_path == ["Retrieval Augmented Generation", "Hybrid retrieval"]


def test_content_hash_changes_with_body():
    a = parse(CORPUS / "hockey.md", CORPUS)
    b = parse(CORPUS / "hockey.md", CORPUS)
    assert a.content_hash == b.content_hash


def test_new_document_text():
    fname, content = new_document_text("Some note about foxes.", title="Fox facts",
                                       tags=["animals"], source="chat")
    assert fname == "fox-facts.md"
    assert content.startswith("---\n")
    assert "title: Fox facts" in content
    assert "tags:" in content and "animals" in content
    assert "# Fox facts" in content
