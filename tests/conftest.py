"""Offline test setup: config reads env lazily, so we just set env vars and stub
the LLM module's network functions."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fake_vector(text: str, dim: int = 1024) -> list[float]:
    h = hashlib.sha256(text.lower().encode()).digest()
    raw = (h * (dim // len(h) + 1))[:dim]
    vals = [(b - 128) / 128 for b in raw]
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    shutil.copytree(FIXTURES / "corpus", root / "corpus")
    shutil.copytree(FIXTURES / "attachments", root / "attachments")
    (root / "queue").mkdir()

    monkeypatch.setenv("MCP_WIKI_DIR", str(root))
    monkeypatch.setenv("MCP_WIKI_DB", str(tmp_path / "wiki.db"))
    monkeypatch.setenv("MCP_WIKI_LLM_KEY", "test")

    from mcp_wiki import doc, images, index, ingest, llm, retrieve, server, store

    monkeypatch.setattr(llm, "embed", lambda texts, **kw: [fake_vector(t) for t in texts])
    monkeypatch.setattr(llm, "chat", lambda messages, **kw: "STUB ANSWER [1]")
    monkeypatch.setattr(llm, "caption_image", lambda uri, alt: f"caption of {alt or 'image'}")

    return SimpleNamespace(root=root, doc=doc, images=images, index=index,
                           ingest=ingest, llm=llm, retrieve=retrieve, server=server,
                           store=store)
