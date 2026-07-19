"""
Thin wrapper around Groq's OpenAI-compatible chat completions endpoint.

Usage:
    from eliteprocareers.generation.llm_client import generate_text
    text = generate_text("Say hello in one sentence.")
"""

import httpx

from eliteprocareers.config import settings

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(Exception):
    """Raised when the LLM API returns a non-2xx response or an
    unexpected payload shape."""


def generate_text(prompt: str, temperature: float = 0.7) -> str:
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    response = httpx.post(GROQ_URL, headers=headers, json=payload, timeout=30)

    if response.status_code >= 400:
        raise LLMError(
            f"Groq API request failed ({response.status_code}): {response.text}"
        )

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected Groq response shape: {data}") from e
