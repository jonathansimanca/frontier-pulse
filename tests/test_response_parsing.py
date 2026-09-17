"""Regression tests for parsing grounded Gemini discovery responses.

Real responses repeatedly contain a corrupted array opener ('"key_takeaways":.",' with the "["
and first element missing). The old parser failed on the whole document and its per-item
fallback silently dropped every affected item, which removed the frontier-lab CEO slowdown
story from discovery in 6 of 6 live probe calls for the 2026-09-15 window.
"""

import json
import re
from pathlib import Path

import pytest

import src.ia_news_researcher as researcher
from conftest import FakeGenAIClient, candidates_from_selection_prompt, discovery_response, selection_response
from src.editorial_priority import classify_priority
from src.ia_news_researcher import parse_json_from_response, parse_json_with_diagnostics, repair_corrupted_array_openers
from src.research_audit import AUDIT_FILENAME

FIXTURES = Path(__file__).parent / "fixtures"
RESPONSES = json.loads((FIXTURES / "grounded_raw_responses.json").read_text(encoding="utf-8"))["responses"]
CORRUPTED = [r for r in RESPONSES if r["corrupted"]]
BY_NAME = {r["name"]: r for r in RESPONSES}


def _strip_fences(text):
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    return re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()


def _is_valid_json(text):
    try:
        json.loads(_strip_fences(text))
        return True
    except json.JSONDecodeError:
        return False


@pytest.mark.parametrize("response", CORRUPTED, ids=lambda r: r["name"])
def test_fixture_reproduces_the_corruption(response):
    assert '"key_takeaways":.",' in response["raw_text"]
    assert not _is_valid_json(response["raw_text"])


@pytest.mark.parametrize("response", RESPONSES, ids=lambda r: r["name"])
def test_every_item_in_a_real_response_is_recovered(response):
    raw_ids = re.findall(r'"id":\s*"([^"]+)"', response["raw_text"])

    parsed, diagnostics = parse_json_with_diagnostics(response["raw_text"])

    assert [item["id"] for item in parsed["items"]] == raw_ids
    assert diagnostics["raw_item_count"] == diagnostics["parsed_item_count"] == len(raw_ids)
    if response["corrupted"]:
        assert diagnostics["strategy"] == "repaired"
        assert diagnostics["repairs"] == response["raw_text"].count('"key_takeaways":.",')
        for item in parsed["items"]:
            assert isinstance(item["key_takeaways"], list) and item["key_takeaways"]
    else:
        assert (diagnostics["strategy"], diagnostics["repairs"]) == ("direct", 0)


def test_slowdown_story_is_parsed_and_flagged_from_the_corrupted_probe_response():
    parsed = parse_json_from_response(BY_NAME["safety_2026-09-15_run1"]["raw_text"])
    first = parsed["items"][0]

    assert "Pace the Frontier" in first["summary"]
    assert classify_priority(first).flagged
    assert any("washingtonpost.com" in src["url"] for src in first["sources"])


def test_repair_only_touches_corrupted_openers():
    valid = '{\n  "key_takeaways": [\n    "a"\n  ],\n  "sources": [\n    {"url": "https://x.test"}\n  ],\n  "summary": "Uses key_takeaways: literally."\n}'
    assert repair_corrupted_array_openers(valid) == (valid, 0)

    multiline_valid = '{\n  "key_takeaways":\n  [\n    "a"\n  ]\n}'
    assert repair_corrupted_array_openers(multiline_valid) == (multiline_valid, 0)

    corrupted_sources = '{\n  "id": "x",\n  "sources":.",\n    {"url": "https://x.test"}\n  ]\n}'
    repaired, count = repair_corrupted_array_openers(corrupted_sources)
    assert count == 1
    assert json.loads(repaired)["sources"] == [{"url": "https://x.test"}]


def test_pipeline_keeps_items_from_a_corrupted_discovery_response(research_env):
    raw = BY_NAME["safety_2026-09-15_run1"]["raw_text"]
    raw_ids = re.findall(r'"id":\s*"([^"]+)"', raw)

    def discovery(track, model, attempt, prompt):
        if track == "frontier_safety_and_governance":
            response = discovery_response([], queries=("AI CEOs call for AI slowdown September 2026",))
            response.text = raw
            return response
        return discovery_response([])

    def editor(model, prompt, attempt):
        candidates = candidates_from_selection_prompt(prompt)
        return selection_response(candidates, [candidates[0]["id"]], edition_date="2026-09-15")

    client = research_env.install_client(FakeGenAIClient(discovery, editor))
    researcher.research_ai_news("2026-09-15")

    selection_prompt = client.models.selection_prompts[0]
    for item_id in raw_ids:
        assert item_id in selection_prompt
    assert "DETERMINISTIC PRIORITY SIGNALS" in selection_prompt

    audit = json.loads((research_env.edition_dir("2026-09-15") / AUDIT_FILENAME).read_text(encoding="utf-8"))
    track = next(t for t in audit["tracks"] if t["track"] == "frontier_safety_and_governance")
    assert [c["id"] for c in track["candidates"]] == raw_ids

    attempt = track["attempts"][0]
    assert attempt["parse_strategy"] == "repaired"
    assert attempt["parse_repairs"] == raw.count('"key_takeaways":.",')
    assert attempt["raw_item_count"] == attempt["parsed_item_count"] == len(raw_ids)
    assert attempt["raw_response"] == raw


# --- Audit visibility of parse losses -------------------------------------------------


def _discovery_returning(track_key, text):
    def discovery(track, model, attempt, prompt):
        if track == track_key:
            response = discovery_response([], queries=("q September 2026",))
            response.text = text
            return response
        return discovery_response([])
    return discovery


def _first_candidate_editor(model, prompt, attempt):
    candidates = candidates_from_selection_prompt(prompt)
    return selection_response(candidates, [candidates[0]["id"]], edition_date="2026-09-15")


def test_audit_exposes_items_lost_by_the_parser(research_env, capsys):
    """An unrecoverable item must show up as raw_item_count > parsed_item_count in the audit."""
    good = '{"id": "good", "title": "Good Story", "category": "C", "summary": "S", "why_it_matters": "W", "key_takeaways": ["K"], "sources": [{"title": "T", "url": "https://techcrunch.com/good"}]}'
    broken = '{"id": "broken", "title": "Broken "quoted" Story", "category": "C", "summary": "S", "why_it_matters": "W", "key_takeaways": ["K"], "sources": [{"title": "T", "url": "https://techcrunch.com/broken"}]}'
    raw = '```json\n{"items": [\n' + good + ',\n' + broken + '\n]}\n```'

    research_env.install_client(FakeGenAIClient(_discovery_returning("frontier_labs", raw), _first_candidate_editor))
    researcher.research_ai_news("2026-09-15")

    audit = json.loads((research_env.edition_dir("2026-09-15") / AUDIT_FILENAME).read_text(encoding="utf-8"))
    attempt = next(t for t in audit["tracks"] if t["track"] == "frontier_labs")["attempts"][0]
    assert attempt["parse_strategy"] == "item_fallback"
    assert (attempt["raw_item_count"], attempt["parsed_item_count"]) == (2, 1)
    assert attempt["raw_response"] == raw
    assert "parse kept 1 of 2 items" in capsys.readouterr().out


def test_audit_keeps_raw_response_of_unparseable_attempts(research_env):
    raw = "Here are the stories I found: none in valid JSON, sorry."

    research_env.install_client(FakeGenAIClient(_discovery_returning("frontier_labs", raw), _first_candidate_editor))
    with pytest.raises(RuntimeError):
        researcher.research_ai_news("2026-09-15")

    audit = json.loads((research_env.edition_dir("2026-09-15") / AUDIT_FILENAME).read_text(encoding="utf-8"))
    attempts = next(t for t in audit["tracks"] if t["track"] == "frontier_labs")["attempts"]
    assert [a["status"] for a in attempts] == ["error", "error", "error"]
    assert all(a["raw_response"] == raw and a["raw_item_count"] == 0 for a in attempts)
    assert all("Failed to parse JSON" in a["error"] for a in attempts)
