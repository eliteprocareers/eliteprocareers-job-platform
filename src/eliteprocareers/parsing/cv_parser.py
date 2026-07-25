"""
CV parsing -- takes raw extracted CV text, sends it to the LLM with an
extraction prompt, and parses the result into a ParsedCVProfile.

Structurally the mirror of generation/cv_tailoring.py's prompt-build ->
LLM call -> JSON-parse pipeline, just running in the opposite direction
(unstructured text -> structured fields, instead of structured fields ->
generated text).
"""
import json

from eliteprocareers.generation.llm_client import GROQ_MODEL, generate_text
from eliteprocareers.profiles.models import ParsedCVProfile


class CVParsingError(Exception):
    """Raised when the LLM response can't be parsed into a valid
    ParsedCVProfile."""


def build_extraction_prompt(raw_text: str) -> str:
    return f"""You are extracting structured data from a candidate's CV/resume.
Below is the raw text extracted from their uploaded file (formatting,
line breaks, and spacing may be imperfect -- this came from an automated
PDF/DOCX text extraction, not a clean copy-paste).

RAW CV TEXT:
---
{raw_text}
---

Extract ONLY information that is actually present in the text above --
do not invent, infer, or embellish any detail (no fabricated dates,
companies, degrees, or skills). If a field isn't present in the CV,
omit it or use an empty list/null, whichever the shape below expects.

Respond with ONLY valid JSON (no markdown, no code fences, no
commentary) matching exactly this shape:

{{
  "full_name": "string or null",
  "headline": "string or null (e.g. current job title/professional title line)",
  "summary": "string or null (professional summary/objective, if present)",
  "location": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "linkedin_url": "string or null",
  "portfolio_url": "string or null",
  "skills": ["skill1", "skill2", ...],
  "work_experience": [
    {{
      "company": "...",
      "title": "...",
      "location": "string or null",
      "start_date_text": "string or null (keep exactly as written, e.g. 'Jan 2019')",
      "end_date_text": "string or null (keep exactly as written)",
      "is_current": true or false,
      "description": "string or null"
    }}
  ],
  "education": [
    {{
      "institution": "...",
      "degree": "string or null",
      "field_of_study": "string or null",
      "start_date_text": "string or null",
      "end_date_text": "string or null"
    }}
  ],
  "certifications": [
    {{"name": "...", "issuer": "string or null"}}
  ],
  "languages": [
    {{"language": "...", "proficiency": "basic|conversational|fluent|native or null"}}
  ],
  "projects": [
    {{"name": "...", "description": "string or null", "url": "string or null"}}
  ]
}}"""


def _strip_markdown_fences(raw: str) -> str:
    """Same tolerance as cv_tailoring.py's _strip_markdown_fences --
    LLMs wrap JSON in ```json blocks even when explicitly told not to.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def parse_extraction_response(raw: str) -> ParsedCVProfile:
    cleaned = _strip_markdown_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise CVParsingError(
            f"LLM response was not valid JSON: {e}\nRaw response:\n{raw}"
        ) from e

    try:
        return ParsedCVProfile.model_validate(data)
    except Exception as e:
        raise CVParsingError(
            f"LLM response JSON didn't match ParsedCVProfile shape: {e}\n"
            f"Parsed data:\n{data}"
        ) from e


def extract_cv_profile(raw_text: str) -> ParsedCVProfile:
    """Full text-to-structure pipeline: build prompt -> call LLM -> parse.
    Caller (parsing/pipeline.py) is responsible for persisting the result.
    """
    prompt = build_extraction_prompt(raw_text)
    raw_response = generate_text(prompt, temperature=0.2, model=GROQ_MODEL)
    return parse_extraction_response(raw_response)
