"""
Thin LLM client. Optional: the platform runs end-to-end without any key
(heuristic classifier + template generator), and switches to a real LLM by
setting LLM_PROVIDER=openai (needs OPENAI_API_KEY),
LLM_PROVIDER=openrouter (needs OPENROUTER_API_KEY) or LLM_PROVIDER=ollama
(needs a local Ollama server).

OpenRouter and OpenAI share the /chat/completions wire format, so both go
through _openai_style(); only the base URL, key and model id differ.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any


def _post_json(url: str, payload: dict, headers: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _openai_style(base_url: str, api_key: str, model: str, system: str | None,
                  prompt: str, temperature: float, max_tokens: int,
                  extra_headers: dict | None = None) -> str:
    """POST to any OpenAI-compatible /chat/completions endpoint."""
    headers = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    data = _post_json(
        f"{base_url}/chat/completions",
        {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": system or "You are a senior technical writer.",
                },
                {"role": "user", "content": prompt},
            ],
        },
        headers,
    )
    return data["choices"][0]["message"]["content"].strip()


def chat(prompt: str, settings, system: str | None = None,
         temperature: float = 0.7, max_tokens: int = 1600) -> str:
    """Plain-text completion. Raises on failure; callers fall back."""
    if settings.llm_provider == "openai":
        return _openai_style(
            settings.openai_base_url, settings.openai_api_key,
            settings.active_llm_model, system, prompt,
            temperature, max_tokens,
        )

    if settings.llm_provider == "openrouter":
        # OpenRouter takes the same body as OpenAI. HTTP-Referer / X-Title are
        # optional attribution headers that show up on the user's dashboard.
        return _openai_style(
            settings.openrouter_base_url, settings.openrouter_api_key,
            settings.active_llm_model, system, prompt,
            temperature, max_tokens,
            {
                "HTTP-Referer": settings.openrouter_referer,
                "X-Title": settings.openrouter_title,
            },
        )

    if settings.llm_provider == "ollama":
        data = _post_json(
            f"{settings.ollama_url}/api/generate",
            {
                "model": settings.active_llm_model,
                "prompt": f"{system or ''}\n\n{prompt}".strip(),
                "stream": False,
                "options": {"temperature": temperature},
            },
            {},
            timeout=180.0,
        )
        return data.get("response", "").strip()

    raise RuntimeError(f"unknown LLM_PROVIDER={settings.llm_provider!r}")


def chat_json(prompt: str, settings) -> Any:
    """Completion parsed as JSON, tolerating ```json fences and stray prose."""
    raw = chat(prompt, settings, temperature=0.2, max_tokens=900)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}|\[.*\]", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None
