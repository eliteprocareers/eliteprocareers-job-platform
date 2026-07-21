"""
Thin wrapper around Groq's OpenAI-compatible chat completions endpoint.

Usage:
    from eliteprocareers.generation.llm_client import generate_text
    text = generate_text("Say hello in one sentence.")
"""

import re
import time

import httpx

from eliteprocareers.config import settings

GROQ_MODEL = "llama-3.3-70b-versatile"
# Free-tier daily budgets differ hugely by model (confirmed live 2026-07-20
# after llama-3.3-70b-versatile's 100,000 TPD cap got hit mid-backfill):
# 70b-versatile is 100,000 tokens/day; 8b-instant is 500,000 tokens/day.
# Callers doing short, low-stakes generation (e.g. a 2-3 sentence match
# rationale) should use the fast model to get 5x the daily headroom --
# GROQ_MODEL stays the default for anything quality-sensitive (cover
# letters, screening answers) where that tradeoff isn't worth it.
GROQ_MODEL_FAST = "llama-3.1-8b-instant"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Groq's on-demand tier caps llama-3.3-70b-versatile at 12,000 tokens/minute
# (confirmed live 2026-07-20 via a real 429 during backfill_match_rationales.py:
# "Limit 12000, Used 11674, Requested 2694"). A ~2,600-2,700 token prompt (full
# profile + job description) means ~4 calls/min before hitting it -- routine
# for any script processing more than a handful of rows, not an edge case.
_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s")


class LLMError(Exception):
    """Raised when the LLM API returns a non-2xx response (after retries,
    for 429s) or an unexpected payload shape."""


def generate_text(
    prompt: str,
    temperature: float = 0.7,
    max_retries: int = 5,
    model: str = GROQ_MODEL,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    attempt = 0
    while True:
        response = httpx.post(GROQ_URL, headers=headers, json=payload, timeout=30)

        if response.status_code == 429 and attempt < max_retries:
            attempt += 1
            wait_seconds = _rate_limit_wait_seconds(response)
            time.sleep(wait_seconds)
            continue

        if response.status_code >= 400:
            raise LLMError(
                f"Groq API request failed ({response.status_code}): {response.text}"
            )

        break

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected Groq response shape: {data}") from e


def _rate_limit_wait_seconds(response: httpx.Response) -> float:
    """Figures out how long to sleep before retrying a 429.

    Prefers the standard Retry-After header if Groq sends one; falls back
    to parsing "Please try again in 11.84s" out of the JSON error body
    (the actual shape confirmed live 2026-07-20); falls back to a flat 15s
    if neither is present. Always adds a 0.5s buffer since a retry that
    lands a beat early just draws another 429.

    Hard-capped at 60s no matter what the source says. Retry-After per
    RFC 7231 is allowed to be an HTTP-date instead of a seconds-count --
    if a value like that (or any other malformed/huge number) slipped
    past the float() parse, an uncapped version of this would hand
    time.sleep() an enormous number and the script would sit there for
    hours with no error and no output, which looks exactly like a hang.
    A rate-limit wait that's actually longer than 60s isn't something
    this script should sit through silently anyway -- better to error
    out via max_retries and let the caller decide.
    """
    header_value = response.headers.get("retry-after")
    if header_value is not None:
        try:
            return min(float(header_value) + 0.5, 60.0)
        except ValueError:
            pass

    match = _RETRY_AFTER_RE.search(response.text)
    if match:
        return min(float(match.group(1)) + 0.5, 60.0)

    return 15.0
