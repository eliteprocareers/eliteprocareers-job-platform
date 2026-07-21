"""Tests for scoring/embeddings.py's pure text-building functions.

Covers build_job_text() only -- specifically approach #7 (title-
reinforcement, accepted v17/v18: see that function's docstring for the
full decision and the known noise tradeoff). Does not test
compute_match_score() itself, since that requires the actual
sentence-transformers model; these tests only lock in the *text* that
gets embedded, which is what approach #7 changed.
"""
from eliteprocareers.scoring.embeddings import build_job_text


def test_title_is_reinforced_at_end_of_job_text():
    """Approach #7: the title must appear twice -- once leading (existing
    behavior) and once trailing (new, v17/v18) -- so it carries more
    weight in the resulting embedding than the description alone."""
    text = build_job_text("Product Manager", "Acme Corp", "Build great products.")
    assert text.startswith("Product Manager at Acme Corp.")
    assert text.rstrip(".").endswith("Product Manager")
    assert text.count("Product Manager") == 2


def test_job_text_with_none_description_still_reinforces_title():
    """No description shouldn't break the trailing title repetition."""
    text = build_job_text("Data Analyst", "Beta Inc", None)
    assert text.count("Data Analyst") == 2


def test_job_text_with_long_description_still_reinforces_title_after_truncation():
    """Truncation happens on the description before the title is
    re-appended -- confirm the trailing title survives the 800-char cap
    and isn't itself truncated away."""
    long_description = "Responsibilities: " + ("build things. " * 200)
    text = build_job_text("Senior Engineer", "Gamma LLC", long_description)
    assert text.rstrip(".").endswith("Senior Engineer")
