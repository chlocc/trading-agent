"""
Shared LLM client.

Two providers are supported: Anthropic (direct) and OpenRouter. Each call
site picks its provider explicitly via the `provider` argument to `chat()`
— nothing here auto-switches globally based on which API keys happen to be
set, so one pipeline step routing through a cheap third party doesn't drag
every other step along with it.

Env vars:
  ANTHROPIC_API_KEY   — required for provider="anthropic"
  OPENROUTER_API_KEY  — required for provider="openrouter"
  OPENROUTER_MODEL    — model ID, defaults to meta-llama/llama-3.3-70b-instruct:free
"""

import asyncio
import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def using_openrouter() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def active_model(anthropic_model: str, openrouter_model: str | None = None) -> str:
    if using_openrouter():
        return openrouter_model or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    return anthropic_model


async def chat(
    system: str,
    user: str,
    max_tokens: int = 4096,
    anthropic_model: str = "claude-haiku-4-5",
    openrouter_model: str | None = None,
    provider: str | None = None,
) -> tuple[str, dict]:
    """Send one system+user exchange, return (text, usage).

    `provider` forces which backend this specific call uses — "anthropic" or
    "openrouter". Pass it explicitly from each call site; if omitted, falls
    back to the legacy auto-detect (openrouter > anthropic, by whichever API
    key is present) for backward compatibility.

    openrouter_model overrides that provider's default model for this call,
    letting different pipeline steps use different models (e.g. a cheap
    model for extraction, a quality model for brief writing).

    usage keys: input, output, cache_write, cache_read (token counts).
    """
    if provider is None:
        provider = "openrouter" if using_openrouter() else "anthropic"

    if provider == "openrouter":
        return await _openrouter_chat(system, user, max_tokens, openrouter_model)
    if provider == "anthropic":
        return await _anthropic_chat(system, user, max_tokens, anthropic_model)
    raise ValueError(f"Unknown provider: {provider!r}")


async def _openrouter_chat(
    system: str, user: str, max_tokens: int, openrouter_model: str | None = None
) -> tuple[str, dict]:
    model = openrouter_model or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}

    async with httpx.AsyncClient(timeout=180) as client:
        last_usage = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
        for attempt in range(4):
            try:
                resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # A hung upstream shouldn't kill the run — back off and retry
                wait = 10 * (attempt + 1)
                print(f"    {type(e).__name__} from OpenRouter, retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            # Free models are limited to 20 req/min — back off and retry on 429
            if resp.status_code == 429:
                wait = 20 * (attempt + 1)
                print(f"    rate-limited by OpenRouter, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            # OpenRouter can return 200 with an error body (e.g. model offline)
            if "error" in data:
                raise RuntimeError(f"OpenRouter error: {data['error']}")
            message = data["choices"][0].get("message") or {}
            u = data.get("usage", {})
            last_usage = {
                "input": u.get("prompt_tokens", 0),
                "output": u.get("completion_tokens", 0),
                "cache_write": 0,
                "cache_read": 0,
            }
            # content can be null (reasoning-only reply, filtered or truncated
            # completion). Fall back to the reasoning field, then retry.
            text = message.get("content") or message.get("reasoning") or ""
            if text.strip():
                return text.strip(), last_usage
            finish = data["choices"][0].get("finish_reason")
            print(f"    empty response from {model} (finish_reason={finish}), retrying...")
            await asyncio.sleep(5)

        # Don't kill the whole pipeline for one bad batch — let the caller skip it
        print(f"    ✗ giving up on this batch after 4 empty/rate-limited attempts")
        return "", last_usage


async def _anthropic_chat(
    system: str, user: str, max_tokens: int, model: str
) -> tuple[str, dict]:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    u = response.usage
    usage = {
        "input": u.input_tokens,
        "output": u.output_tokens,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
    return response.content[0].text.strip(), usage
