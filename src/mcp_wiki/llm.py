"""Thin OpenAI-compatible client for embeddings, chat, and vision. Embeddings
and chat/vision may live on different hosts (see config.llm_base() vs.
config.chat_base()). Standard library only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import config


class LLMError(RuntimeError):
    pass


def _post(path: str, payload: dict, *, base: str | None = None, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(
        (base or config.llm_base()) + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.llm_key()}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"HTTP {exc.code} {path}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMError(f"{type(exc).__name__}: {exc} ({path})") from None


def embed(texts: list[str], *, batch: int = 64) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        data = _post("/embeddings", {"model": config.embed_model(), "input": chunk})
        rows = sorted(data["data"], key=lambda r: r["index"])
        out.extend(r["embedding"] for r in rows)
    return out


def chat(messages: list[dict], *, model: str | None = None,
         temperature: float = 0.2, max_tokens: int = 1024) -> str:
    data = _post("/chat/completions", {
        "model": model or config.chat_model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, base=config.chat_base(), timeout=300.0)
    return data["choices"][0]["message"]["content"] or ""


def caption_image(data_uri: str, alt: str) -> str:
    prompt = (
        "Describe this image for a search index in 1-3 sentences. State what it "
        "shows, any visible text, numbers, or chart/table takeaways. Be concrete."
    )
    if alt:
        prompt += f' The author\'s alt text is: "{alt}".'
    return chat(
        [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ]}],
        model=config.vision_model(), temperature=0.0, max_tokens=200,
    ).strip()
