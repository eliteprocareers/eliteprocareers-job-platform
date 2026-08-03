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


# Added 2026-08-03 after a real CV upload failed validation entirely:
# the prompt explicitly instructs "basic|conversational|fluent|native or
# null" (see build_extraction_prompt above), but Groq still returned
# "Proficient" and "Native" (capitalized, and "Proficient" isn't even
# one of the four listed options) for a real candidate's languages --
# confirmed live, not hypothetical. Prompt instructions alone aren't
# reliable enough for a strict enum field; this is defense-in-depth
# normalization run before Pydantic validation, not a replacement for
# the prompt (which stays as-is -- still gets it right most of the
# time, this just covers the cases it doesn't).
_PROFICIENCY_SYNONYMS: dict[str, str] = {
    "native": "native", "mother tongue": "native", "first language": "native",
    "fluent": "fluent", "advanced": "fluent", "proficient": "fluent", "excellent": "fluent",
    "professional working proficiency": "fluent", "full professional proficiency": "fluent",
    "conversational": "conversational", "intermediate": "conversational",
    "working proficiency": "conversational", "good": "conversational", "moderate": "conversational",
    "basic": "basic", "beginner": "basic", "elementary": "basic", "limited": "basic",
}


def _normalize_language_proficiency(data: dict) -> dict:
    """Maps common freeform proficiency phrasing to the strict
    LanguageProficiency enum, case-insensitively. Anything not
    recognized becomes null rather than failing the entire CV parse --
    proficiency is a minor field; losing it for one language is far
    better than losing the candidate's whole name/work history/skills
    to a validation error over a single unrecognized word.
    """
    languages = data.get("languages")
    if not isinstance(languages, list):
        return data
    for entry in languages:
        if not isinstance(entry, dict):
            continue
        raw_proficiency = entry.get("proficiency")
        if not isinstance(raw_proficiency, str):
            continue
        normalized = _PROFICIENCY_SYNONYMS.get(raw_proficiency.strip().lower())
        entry["proficiency"] = normalized  # None if not recognized -- safe default
    return data


def parse_extraction_response(raw: str) -> ParsedCVProfile:
    cleaned = _strip_markdown_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise CVParsingError(
            f"LLM response was not valid JSON: {e}\nRaw response:\n{raw}"
        ) from e

    data = _normalize_language_proficiency(data)

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
