"""Runtime configuration. Paths and endpoints are read from the environment on
every access so tests (and a relocated wiki) work without reimporting."""

from __future__ import annotations

import os
from pathlib import Path

EMBED_DIM = 1024                       # BGE-M3
CHUNK_MAX_CHARS = 1500
TEXT_EXT = {".md", ".markdown", ".mdx", ".txt", ".rst"}


def wiki_dir() -> Path:
    return Path(os.environ.get("MCP_WIKI_DIR", "~/wiki")).expanduser()


def corpus_dir() -> Path:
    return wiki_dir() / "corpus"


def queue_dir() -> Path:
    return wiki_dir() / "queue"


def attachments_dir() -> Path:
    return wiki_dir() / "attachments"


def db_path() -> Path:
    return Path(
        os.environ.get("MCP_WIKI_DB", "~/.local/state/mcp-wiki/wiki.db")
    ).expanduser()


def llm_base() -> str:
    return os.environ.get("MCP_WIKI_LLM_BASE", "http://127.0.0.1:4000/v1").rstrip("/")


def llm_key() -> str:
    return os.environ.get("MCP_WIKI_LLM_KEY", "")


def embed_model() -> str:
    return os.environ.get("MCP_WIKI_EMBED_MODEL", "embed-local")


def chat_model() -> str:
    return os.environ.get("MCP_WIKI_CHAT_MODEL", "qwen-local")


def vision_model() -> str:
    return os.environ.get("MCP_WIKI_VISION_MODEL", "qwen-local")


def captions_enabled() -> bool:
    return os.environ.get("MCP_WIKI_CAPTIONS", "1") not in ("0", "false", "no")
