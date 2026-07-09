"""LLM judge for the agent-level bench: OpenAI chat completions.

The judge model is deliberately separate from the agent-under-test model
(JUDGE_MODEL env var, default gpt-5-mini) so grader quality does not track
the product config. GPT-5 family models only accept the default temperature,
so the temperature param is omitted for them.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gpt-5-mini")
BASE_URL = os.environ.get("JUDGE_BASE_URL", "https://api.openai.com/v1/chat/completions")


def _api_key() -> str:
    if "openrouter" in BASE_URL:
        key = os.environ.get("OPENROUTER_API_KEY")
    else:
        key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("judge API key not set (source .env)")
    return key


def judge(system: str, user: str, retries: int = 3) -> dict[str, Any]:
    """Call the judge model; expects a JSON object in the reply and parses it."""
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            resp = httpx.post(
                BASE_URL,
                headers={"Authorization": f"Bearer {_api_key()}"},
                json={
                    "model": JUDGE_MODEL,
                    **(
                        {}
                        if JUDGE_MODEL.startswith(("gpt-5", "o1", "o3", "o4"))
                        else {"temperature": 0}
                    ),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if not m:
                raise ValueError(f"no JSON object in judge reply: {content[:200]}")
            return json.loads(m.group(0))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"judge failed after {retries} tries: {last_err}")
