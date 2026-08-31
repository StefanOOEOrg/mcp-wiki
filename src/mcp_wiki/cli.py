"""Command line entry point. With no subcommand it starts the MCP server
(stdio) — that is how the ``mcp_servers`` config launches it."""

from __future__ import annotations

import argparse
import json
import sys

from . import index, retrieve, store


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("serve", "-m"):
        from .server import main as serve
        serve()
        return

    ap = argparse.ArgumentParser(prog="mcp-wiki")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="build/refresh the index from the corpus")
    p_index.add_argument("path", nargs="?", default=None)
    p_index.add_argument("--full", action="store_true")
    p_index.add_argument("-v", "--verbose", action="store_true")

    p_search = sub.add_parser("search", help="hybrid search")
    p_search.add_argument("query")
    p_search.add_argument("-k", type=int, default=8)

    p_answer = sub.add_parser("answer", help="retrieve and answer")
    p_answer.add_argument("query")

    sub.add_parser("ingest-queue", help="process the drop-zone")
    sub.add_parser("stats", help="index statistics")

    args = ap.parse_args(argv)
    db = store.connect()
    try:
        if args.cmd == "index":
            counts = index.reindex(db, args.path, full=args.full, verbose=args.verbose)
            print(json.dumps({**counts, **store.stats(db)}, indent=2))
        elif args.cmd == "search":
            for hit in retrieve.search(db, args.query, k=args.k):
                heads = "; ".join(" › ".join(h["heading_path"])
                                  for h in hit["hits"] if h["heading_path"])
                print(f"{hit['score']:.3f}  {hit['path']}"
                      + (f"  [{hit['section']}]" if hit["section"] else "")
                      + (f"  ({heads})" if heads else ""))
                for h in hit["hits"]:
                    print(f"        {h['snippet']}")
        elif args.cmd == "answer":
            res = retrieve.answer(db, args.query)
            print(res["answer"])
            print("\nSources:")
            for s in res["sources"]:
                print(f"  [{s['n']}] {s['path']}")
        elif args.cmd == "ingest-queue":
            from .ingest import ingest_queue
            print(json.dumps(ingest_queue(db), indent=2))
        elif args.cmd == "stats":
            print(json.dumps(store.stats(db), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
