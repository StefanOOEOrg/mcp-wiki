# systemd (user) units

Auto-ingest whatever lands in `~/wiki/queue/`.

```bash
cp mcp-wiki.env.example ~/.config/mcp-wiki.env && chmod 600 ~/.config/mcp-wiki.env
# fill in MCP_WIKI_LLM_KEY

cp mcp-wiki-ingest.{service,path,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now mcp-wiki-ingest.path mcp-wiki-ingest.timer
```

`.path` fires on any change under `queue/`; `.timer` is a 5-minute fallback sweep.
Both trigger the oneshot `.service` → `mcp_wiki ingest-queue`.
