# mcp-wiki

A local **RAG document store** over a folder of markdown, exposed as an
[MCP](https://modelcontextprotocol.io) server. Drop documents in, ask questions,
get cited answers — no service to run beyond SQLite and an embedding endpoint.

- **Store:** one SQLite file — `sqlite-vec` for dense vectors, FTS5 for keyword
  search, hybrid-merged with Reciprocal Rank Fusion.
- **Embeddings / chat:** any OpenAI-compatible endpoint (built for a local
  [litellm](https://github.com/BerriAI/litellm) proxy in front of vLLM).
- **Multilingual** (BGE-M3 by default), **tables** kept whole, **images**
  captioned by a vision model at index time and made searchable as text.
- **Writable:** `wiki_add` / `wiki_update` / `wiki_remove` tools, plus a
  drop-zone folder that is ingested automatically.

Not a curated wiki — no enforced schema, no cross-link maintenance. Documents are
whatever markdown you put in `corpus/`; YAML frontmatter (`title`, `type`,
`tags`) is used as metadata when present.

## Layout

```
$MCP_WIKI_DIR (default ~/wiki)
├── corpus/        the documents (markdown), any sub-folders → a "section" tag
├── queue/         drop files here → moved into corpus/inbox/ and indexed
└── attachments/   images referenced from documents
$MCP_WIKI_DB (default ~/.local/state/mcp-wiki/wiki.db)   the derived index
```

## Configure (all env vars)

| Var | Default |
|---|---|
| `MCP_WIKI_DIR` | `~/wiki` |
| `MCP_WIKI_DB` | `~/.local/state/mcp-wiki/wiki.db` |
| `MCP_WIKI_LLM_BASE` | `http://127.0.0.1:4000/v1` (embeddings endpoint) |
| `MCP_WIKI_CHAT_BASE` | = `MCP_WIKI_LLM_BASE` (chat/vision endpoint, if different) |
| `MCP_WIKI_LLM_KEY` | *(empty — optional; no Authorization header is sent when unset)* |
| `MCP_WIKI_EMBED_MODEL` | `embed-local` |
| `MCP_WIKI_CHAT_MODEL` / `MCP_WIKI_VISION_MODEL` | `qwen-local` |
| `MCP_WIKI_CAPTIONS` | `1` (set `0` to skip image captioning) |

## Use

```bash
mcp-wiki index                       # build/refresh the index
mcp-wiki search "some question"
mcp-wiki answer "some question"
mcp-wiki ingest-queue                # process the drop-zone
mcp-wiki                             # no args → MCP server on stdio
```

### MCP client config

```json
{ "mcpServers": { "wiki": { "command": "mcp-wiki", "env": { "MCP_WIKI_LLM_BASE": "http://host:8001/v1" } } } }
```

### Tools

`wiki_search(query, k, section?, tags?)` · `wiki_get(path)` ·
`wiki_answer(query, k)` · `wiki_stats()` · `wiki_add(text, title?, tags?, section?, source?)` ·
`wiki_update(path, text)` · `wiki_remove(path)` · `wiki_reindex(full?)` ·
`wiki_ingest_queue()`

## Development

```bash
uv pip install -e ".[dev]"
pytest            # offline; embeddings/chat are stubbed
ruff check src tests
```

## License

MIT — see [LICENSE](LICENSE).
