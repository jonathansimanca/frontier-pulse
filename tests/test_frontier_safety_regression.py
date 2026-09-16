"""End-to-end regression test for the 2026-09-14 missed frontier AI safety story.

Test 3 of the remediation: a coordinated slowdown / safety story involving multiple frontier
labs must survive discovery, source filtering, pool validation, historical deduplication,
editorial selection, the priority guard, and the editorial quality gate, and the research
audit must show that path.

Fixtures (no network):
- ``discovery_probe_2026-09-14_run2.json``: live discovery responses captured for the
  2026-09-14 window. Both the ``frontier_safety_and_governance`` and ``frontier_labs`` tracks
  returned the "We Must Pace the Frontier" story under different titles and source URLs.
- ``candidates_2026-09-14.json``: the real 19-candidate production pool, used as the other tracks.
- ``history_2026-09-09.json``: the history production used for deduplication on 2026-09-14.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import src.ia_news_researcher as researcher
from conftest import FakeGenAIClient, candidates_from_selection_prompt, selection_response
from src.config import RESEARCH_TRACKS
from src.editorial_priority import classify_priority
from src.quality_gate import validate_edition_quality
from src.research_audit import AUDIT_FILENAME

FIXTURES = Path(__file__).parent / "fixtures"
EDITION_DATE = "2026-09-14"
SAFETY_TRACK = "frontier_safety_and_governance"
LABS_TRACK = "frontier_labs"

SAFETY_VERSION_ID = "amodei-paces-frontier-ai-evaluators"
LABS_VERSION_ID = "amodei-we-must-pace-the-frontier-safety-coalition"

# Titles of the four stories production actually selected on 2026-09-14.
PRODUCTION_SELECTION_PREFIXES = (
    "Amazon and Qualcomm Forge",
    "Mistral AI Secures",
    "AWS and vLLM Partner",
    "Google Commits",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PROBE = _load("discovery_probe_2026-09-14_run2.json")
PRODUCTION_CANDIDATES = _load("candidates_2026-09-14.json")["items"]
HISTORY = _load("history_2026-09-09.json")

OTHER_TRACKS = [track for track in RESEARCH_TRACKS if track not in (SAFETY_TRACK, LABS_TRACK)]
PRODUCTION_BY_TRACK = {track: PRODUCTION_CANDIDATES[i :: len(OTHER_TRACKS)] for i, track in enumerate(OTHER_TRACKS)}


def _production_ids(prefixes=PRODUCTION_SELECTION_PREFIXES) -> list[str]:
    ids = [c["id"] for c in PRODUCTION_CANDIDATES if c["title"].startswith(prefixes)]
    assert len(ids) == len(prefixes)
    return ids


def _grounded_response(items: list[dict], queries: list[str], grounding_sources: list[dict]) -> SimpleNamespace:
    metadata = SimpleNamespace(
        web_search_queries=queries,
        grounding_chunks=[SimpleNamespace(web=SimpleNamespace(uri=g.get("uri"), title=g.get("title"))) for g in grounding_sources],
    )
    return SimpleNamespace(
        text="```json\n" + json.dumps({"items": items}) + "\n```",
        candidates=[SimpleNamespace(grounding_metadata=metadata)],
    )


def _discovery_handler(track, model, attempt, prompt):
    if track in PROBE["tracks"]:
        captured = PROBE["tracks"][track]
        return _grounded_response(captured["items"], captured["web_search_queries"], captured["grounding_sources"])
    return _grounded_response(PRODUCTION_BY_TRACK[track], [f"{track} search"], [])


def _editor_choosing(ids: list[str]):
    def handler(model, prompt, attempt):
        return selection_response(candidates_from_selection_prompt(prompt), ids)
    return handler


def _run_pipeline(research_env, selected_ids: list[str]):
    research_env.write_history(HISTORY)
    client = research_env.install_client(FakeGenAIClient(_discovery_handler, _editor_choosing(selected_ids)))
    news_data = researcher.research_ai_news(EDITION_DATE)
    audit = json.loads((research_env.edition_dir(EDITION_DATE) / AUDIT_FILENAME).read_text(encoding="utf-8"))
    return news_data, audit, client


def _candidate(audit: dict, track: str, candidate_id: str) -> dict:
    track_audit = next(t for t in audit["tracks"] if t["track"] == track)
    return next(c for c in track_audit["candidates"] if c["id"] == candidate_id)


def test_fixtures_reproduce_the_2026_09_14_conditions():
    safety_story = PROBE["tracks"][SAFETY_TRACK]["items"][0]
    labs_story = PROBE["tracks"][LABS_TRACK]["items"][0]
    assert (safety_story["id"], labs_story["id"]) == (SAFETY_VERSION_ID, LABS_VERSION_ID)
    assert classify_priority(safety_story).flagged and classify_priority(labs_story).flagged
    assert "pace" in safety_story["title"].lower() and "pace" in labs_story["title"].lower()
    # Same event, different titles and no shared source URL: plain id/title/URL matching cannot merge them.
    assert {s["url"] for s in safety_story["sources"]}.isdisjoint({s["url"] for s in labs_story["sources"]})
    # None of the real production candidates is flagged.
    assert not any(classify_priority(c).flagged for c in PRODUCTION_CANDIDATES)


def test_slowdown_story_survives_every_stage_when_model_repeats_the_production_selection(research_env):
    """Reproduces 2026-09-14: the editor picks the four infrastructure/funding stories again."""
    news_data, audit, client = _run_pipeline(research_env, _production_ids())

    # Discovery: the dedicated track ran and found the story.
    assert [t["track"] for t in audit["tracks"]] == list(RESEARCH_TRACKS)
    safety_candidate = _candidate(audit, SAFETY_TRACK, SAFETY_VERSION_ID)

    # Filtering, pool validation and historical deduplication kept it.
    pool = json.loads((research_env.edition_dir(EDITION_DATE) / "candidates.json").read_text(encoding="utf-8"))
    assert SAFETY_VERSION_ID in {c["id"] for c in pool["items"]}
    assert audit["deduplication"]["history_editions_loaded"] == 1

    # Selection: the prompt flagged it and applied the new rubric.
    selection_prompt = client.models.selection_prompts[0]
    assert "DETERMINISTIC PRIORITY SIGNALS" in selection_prompt
    assert f"id='{SAFETY_VERSION_ID}'" in selection_prompt
    assert "Funding rounds, valuations, and commercial or infrastructure partnerships. These are AT MOST TIER 2" in selection_prompt
    assert "describe the same event" in selection_prompt

    # Priority guard: exactly one version of the event is added, never a duplicate.
    ids = [item["id"] for item in news_data["items"]]
    assert ids[:4] == _production_ids()
    assert ids[4] == SAFETY_VERSION_ID
    assert LABS_VERSION_ID not in ids
    added = news_data["items"][4]
    assert added["relevance_score"] == 5
    assert added["selection_reason"].startswith("Deterministic priority inclusion")

    guard = audit["selection"]["priority_guard"]
    actions = {d["candidate_id"]: d["action"] for d in guard["decisions"]}
    assert actions == {SAFETY_VERSION_ID: "included", LABS_VERSION_ID: "skipped_inclusion_limit_reached"}
    included = next(d for d in guard["decisions"] if d["candidate_id"] == SAFETY_VERSION_ID)
    assert included["grounding_corroborated"] is True
    assert "theguardian.com" in included["grounding_note"]

    # Audit shows the full path for the story and its duplicate.
    assert safety_candidate["outcome"] == "priority_included"
    assert _candidate(audit, LABS_TRACK, LABS_VERSION_ID)["outcome"] == "not_selected"
    for track in audit["tracks"]:
        for attempt in track["attempts"]:
            assert attempt["grounded"] is True

    # Persisted outputs contain the story.
    edition_file = json.loads((research_env.edition_dir(EDITION_DATE) / "edition.json").read_text(encoding="utf-8"))
    history_file = json.loads((research_env.history_dir / f"history_{EDITION_DATE}.json").read_text(encoding="utf-8"))
    assert SAFETY_VERSION_ID in [i["id"] for i in edition_file["items"]]
    assert SAFETY_VERSION_ID in [i["id"] for i in history_file["items"]]

    # Validation: the editorial quality gate accepts the edition.
    report = validate_edition_quality(news_data)
    assert report.passed, report.reasons_for_failure


def test_guard_does_not_add_a_duplicate_when_model_selects_another_version(research_env):
    selected = [LABS_VERSION_ID] + _production_ids()[:3]
    news_data, audit, _ = _run_pipeline(research_env, selected)

    ids = [item["id"] for item in news_data["items"]]
    assert ids == selected
    pace_stories = [i for i in news_data["items"] if "pace" in i["title"].lower()]
    assert len(pace_stories) == 1

    guard = audit["selection"]["priority_guard"]
    actions = {d["candidate_id"]: d["action"] for d in guard["decisions"]}
    assert actions[LABS_VERSION_ID] == "already_selected"
    assert actions[SAFETY_VERSION_ID] == "skipped_priority_story_already_selected"
    assert guard["included_ids"] == []

    assert _candidate(audit, LABS_TRACK, LABS_VERSION_ID)["outcome"] == "selected"
    assert _candidate(audit, SAFETY_TRACK, SAFETY_VERSION_ID)["outcome"] == "not_selected"
    assert validate_edition_quality(news_data).passed


def test_without_the_dedicated_track_coverage_depends_on_a_lucky_frontier_labs_result(research_env, monkeypatch):
    """Without the dedicated track, only frontier_labs can surface the event (it did in 1 of 3 live probe runs)."""
    monkeypatch.setattr(researcher, "RESEARCH_TRACKS", {k: v for k, v in RESEARCH_TRACKS.items() if k != SAFETY_TRACK})

    news_data, audit, _ = _run_pipeline(research_env, _production_ids())

    assert SAFETY_TRACK not in [t["track"] for t in audit["tracks"]]
    ids = [item["id"] for item in news_data["items"]]
    assert SAFETY_VERSION_ID not in ids
    assert ids[-1] == LABS_VERSION_ID
