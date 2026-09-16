"""Tests for the per-edition research audit trail (research_audit.json).

The audit must make a missed story diagnosable as a discovery, filtering, or ranking issue:
every research track records its queries, prompt, model attempts, grounding metadata,
discovered candidates, and the outcome and reason for each candidate.
"""

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import src.ia_news_researcher as researcher
from conftest import (
    FakeGenAIClient,
    candidates_from_selection_prompt,
    discovery_response,
    make_story,
    selection_response,
)
from src.config import GEMINI_RESEARCH_FALLBACK_MODEL, GEMINI_RESEARCH_MODEL, RESEARCH_TRACKS
from src.research_audit import AUDIT_FILENAME, ResearchAuditRecorder, extract_grounding_metadata
from src.schemas import NewsItem, ResearchAudit

EDITION_DATE = "2026-09-14"
SAFETY_TRACK = "frontier_safety_and_governance"
FAILING_TRACK = "benchmarks_safety_and_policy"

SLOWDOWN_STORY = make_story(
    "labs-call-for-slower-frontier-ai",
    "Anthropic, OpenAI and xAI Leaders Call for a Slower Pace of Frontier AI Development",
    urls=("https://www.anthropic.com/news/joint-statement",),
    summary="Leaders of Anthropic, OpenAI and xAI issued a joint statement urging the industry to slow down frontier AI development.",
)

HISTORICAL_URL = "https://techcrunch.com/2026/09/01/already-covered"


def _discovery_items(track: str) -> list[dict]:
    if track == "agentic_and_dev":
        no_sources = make_story("agentic-no-sources", "Agent Framework Without Sources")
        no_sources["sources"] = []
        return [
            make_story("agentic-blocked", "Agent Rumor From Social Media", urls=("https://www.reddit.com/r/ai/1",)),
            make_story("agentic-bad-url", "Agent Story With Broken Link", urls=("not-a-url",)),
            no_sources,
            make_story("agentic-good", "Coding Agent Tops SWE-bench", urls=("https://techcrunch.com/agentic-good",)),
        ]
    if track == "open_source_and_global":
        return [
            make_story("open-repeat", "Open Model Weekly Recap", urls=(HISTORICAL_URL + "/?utm_source=x",)),
            make_story("open-new", "Qwen Releases New Open Weights", urls=("https://huggingface.co/qwen-new",)),
        ]
    if track == SAFETY_TRACK:
        return [SLOWDOWN_STORY]
    return [make_story(f"{track}-{i}", f"{track} headline {i}", urls=(f"https://techcrunch.com/{track}/{i}",)) for i in range(2)]


def _discovery_handler(track, model, attempt, prompt):
    if track == "frontier_labs" and attempt == 1:
        raise RuntimeError("503 UNAVAILABLE: model overloaded")
    if track == FAILING_TRACK:
        return SimpleNamespace(text="I could not find anything useful.", candidates=[])
    return discovery_response(
        _discovery_items(track),
        queries=(f"{track} search one", f"{track} search two"),
        grounding_uris=(f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/{track}",),
    )


def _select_without_safety_story(model, prompt, attempt):
    candidates = candidates_from_selection_prompt(prompt)
    chosen = [c["id"] for c in candidates if c["id"] in {"frontier_labs-0", "agentic-good", "open-new"}]
    return selection_response(candidates, chosen)


def _load_audit(research_env) -> dict:
    path = research_env.edition_dir(EDITION_DATE) / AUDIT_FILENAME
    assert path.exists(), "research_audit.json was not written"
    data = json.loads(path.read_text(encoding="utf-8"))
    ResearchAudit.model_validate(data)
    return data


def _track(audit: dict, track_key: str) -> dict:
    return next(t for t in audit["tracks"] if t["track"] == track_key)


def _candidate(audit: dict, track_key: str, candidate_id: str) -> dict:
    return next(c for c in _track(audit, track_key)["candidates"] if c["id"] == candidate_id)


@pytest.fixture
def completed_audit(research_env):
    research_env.write_history({
        "edition_date": "2026-09-07",
        "items": [{"title": "Unrelated Older Story", "sources": [{"url": HISTORICAL_URL}]}],
    })
    research_env.install_client(FakeGenAIClient(_discovery_handler, _select_without_safety_story))
    news_data = researcher.research_ai_news(EDITION_DATE)
    return _load_audit(research_env), news_data


# --- Unit-level helpers ---------------------------------------------------------------


def test_extract_grounding_metadata_reads_queries_and_sources():
    response = discovery_response([], queries=("q1", "q2", "q1"), grounding_uris=("https://example.com/a",))
    queries, sources = extract_grounding_metadata(response)
    assert queries == ["q1", "q2"]
    assert [(s.title, s.uri) for s in sources] == [("example.com", "https://example.com/a")]

    assert extract_grounding_metadata(SimpleNamespace(text="{}")) == ([], [])
    assert extract_grounding_metadata(SimpleNamespace(candidates=[SimpleNamespace(grounding_metadata=None)])) == ([], [])


def test_filter_candidate_sources_drops_blocked_and_sourceless_candidates_with_events():
    blocked = make_story("blocked", "Blocked", urls=("https://www.reddit.com/x", "https://tiktok.com/y"))
    partially_blocked = make_story("partial", "Partial", urls=("https://reddit.com/x", "https://reuters.com/y"))
    missing = make_story("missing", "Missing")
    missing["sources"] = []
    events: list[dict] = []

    kept = researcher.filter_candidate_sources({"items": [blocked, partially_blocked, missing]}, EDITION_DATE, events=events)

    assert [item["id"] for item in kept] == ["partial"]
    assert [(e["id"], e["stage"]) for e in events] == [("blocked", "blocked_domain_sources"), ("missing", "missing_sources")]
    # No fabricated fallback source is ever created.
    assert all("google.com/search" not in str(src.get("url")) for item in kept for src in item["sources"])
    assert missing["sources"] == []
    assert "reddit.com" in events[0]["reason"] and "tiktok.com" in events[0]["reason"]

    # Legacy call signature keeps working without events.
    assert len(researcher.filter_candidate_sources({"items": [make_story("ok", "Ok")]}, EDITION_DATE)) == 1


def test_deterministic_deduplicate_records_rejection_reasons():
    history = [{"items": [
        {"title": "Anthropic Unveils Claude With Agentic Capabilities", "sources": [{"url": "https://anthropic.com/a/"}]},
    ]}]
    url_dup = NewsItem.model_validate(make_story("url-dup", "Different Title", urls=("https://ANTHROPIC.com/a?ref=1",)))
    title_dup = NewsItem.model_validate(make_story("title-dup", "Anthropic Launches Claude With Agentic Capabilities", urls=("https://x.com/b",)))
    fresh = NewsItem.model_validate(make_story("fresh", "Meta Releases Llama Update", urls=("https://ai.meta.com/c",)))
    rejections: list[dict] = []

    kept = researcher.deterministic_deduplicate([url_dup, title_dup, fresh], history, rejections=rejections)

    assert [c.id for c in kept] == ["fresh"]
    assert [(r["id"], r["stage"]) for r in rejections] == [
        ("url-dup", "historical_url_match"),
        ("title-dup", "historical_title_similarity"),
    ]
    assert "https://anthropic.com/a" in rejections[0]["reason"]
    assert "Anthropic Unveils Claude" in rejections[1]["reason"]


def _recorder_with_track(tmp_path, grounding_sources, queries=()):
    recorder = ResearchAuditRecorder(
        edition_date=EDITION_DATE, start_date=None, end_date=None, output_path=tmp_path / AUDIT_FILENAME,
        research_model="m", fallback_model="f", max_pool_size=35,
    )
    recorder.start_track(SAFETY_TRACK, ["q"], "prompt")
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    recorder.record_track_attempt(
        SAFETY_TRACK, 1, "m", 0.3, now, 10, status="success",
        web_search_queries=queries, grounding_sources=grounding_sources,
    )
    return recorder


def _guard_record_for(candidate):
    return {"decisions": [{"candidate_id": candidate["id"], "title": candidate["title"], "action": "included"}], "included_ids": [candidate["id"]]}


def test_priority_corroboration_true_when_authoritative_domain_is_grounded(tmp_path):
    from src.schemas import GroundingSourceAudit

    candidate = make_story("story", "Story", urls=("https://www.theguardian.com/a", "https://darioamodei.com/b"))
    recorder = _recorder_with_track(tmp_path, [GroundingSourceAudit(title="theguardian.com", uri="https://vertexaisearch.cloud.google.com/r/1")])
    record = _guard_record_for(candidate)

    recorder.annotate_priority_corroboration(record, [candidate], {("story", "Story"): SAFETY_TRACK})

    assert recorder.audit.tracks[0].attempts[0].grounded is True
    assert record["decisions"][0]["grounding_corroborated"] is True
    assert "theguardian.com" in record["decisions"][0]["grounding_note"]


def test_priority_corroboration_false_when_trusted_domain_not_grounded(tmp_path):
    from src.schemas import GroundingSourceAudit

    candidate = make_story("story", "Story", urls=("https://www.reuters.com/a",))
    recorder = _recorder_with_track(tmp_path, [GroundingSourceAudit(title="random-blog.example", uri=None)])
    record = _guard_record_for(candidate)

    recorder.annotate_priority_corroboration(record, [candidate], {("story", "Story"): SAFETY_TRACK})

    assert record["decisions"][0]["grounding_corroborated"] is False


def test_priority_corroboration_unknown_when_attempt_has_no_grounding_metadata(tmp_path):
    candidate = make_story("story", "Story", urls=("https://www.reuters.com/a",))
    recorder = _recorder_with_track(tmp_path, [])
    record = _guard_record_for(candidate)

    recorder.annotate_priority_corroboration(record, [candidate], {("story", "Story"): SAFETY_TRACK})

    assert recorder.audit.tracks[0].attempts[0].grounded is False
    assert record["decisions"][0]["grounding_corroborated"] is None
    assert "no grounding metadata" in record["decisions"][0]["grounding_note"]


def test_audit_save_failure_does_not_raise(tmp_path, capsys):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")

    recorder = ResearchAuditRecorder(
        edition_date=EDITION_DATE,
        start_date=None,
        end_date=None,
        output_path=blocker / AUDIT_FILENAME,
        research_model="m",
        fallback_model="f",
        max_pool_size=35,
        clock=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc),
    )

    assert recorder.save() is False
    assert "Failed to save research audit" in capsys.readouterr().out


# --- End-to-end audit contents --------------------------------------------------------


def test_audit_records_every_track_with_queries_prompt_and_attempts(completed_audit):
    audit, _ = completed_audit

    assert audit["status"] == "completed"
    assert audit["edition_date"] == EDITION_DATE
    assert audit["research_model"] == GEMINI_RESEARCH_MODEL
    assert audit["fallback_model"] == GEMINI_RESEARCH_FALLBACK_MODEL
    assert [t["track"] for t in audit["tracks"]] == list(RESEARCH_TRACKS)

    for track in audit["tracks"]:
        assert track["queries"] == RESEARCH_TRACKS[track["track"]]
        for query in track["queries"]:
            assert f"- {query}" in track["prompt"]
        assert track["prompt_sha256"] == hashlib.sha256(track["prompt"].encode("utf-8")).hexdigest()
        assert track["attempts"], f"No attempts recorded for {track['track']}"
        assert track["finished_at"] is not None


def test_audit_records_retry_with_fallback_model(completed_audit):
    audit, _ = completed_audit
    labs = _track(audit, "frontier_labs")

    assert labs["status"] == "success"
    assert [(a["attempt"], a["model"], a["status"]) for a in labs["attempts"]] == [
        (1, GEMINI_RESEARCH_MODEL, "error"),
        (2, GEMINI_RESEARCH_FALLBACK_MODEL, "success"),
    ]
    assert "503 UNAVAILABLE" in labs["attempts"][0]["error"]
    assert labs["attempts"][0]["temperature"] == 0.3
    assert labs["attempts"][1]["temperature"] == 0.1


def test_audit_records_failed_track_attempts(completed_audit):
    audit, _ = completed_audit
    failed = _track(audit, FAILING_TRACK)

    assert failed["status"] == "failed"
    assert len(failed["attempts"]) == 3
    assert all(a["status"] == "error" and "Failed to parse JSON" in a["error"] for a in failed["attempts"])
    assert failed["candidates"] == []


def test_audit_records_grounding_queries_and_sources(completed_audit):
    audit, _ = completed_audit
    success_attempt = _track(audit, SAFETY_TRACK)["attempts"][0]

    assert success_attempt["web_search_queries"] == [f"{SAFETY_TRACK} search one", f"{SAFETY_TRACK} search two"]
    assert success_attempt["grounding_sources"][0]["uri"].endswith(f"/grounding-api-redirect/{SAFETY_TRACK}")


def test_audit_records_candidates_with_source_urls_and_rejection_reasons(completed_audit):
    audit, _ = completed_audit

    blocked = _candidate(audit, "agentic_and_dev", "agentic-blocked")
    assert blocked["outcome"] == "blocked_domain_sources"
    assert "reddit.com" in blocked["reason"]
    assert blocked["source_urls"] == ["https://www.reddit.com/r/ai/1"]

    bad_url = _candidate(audit, "agentic_and_dev", "agentic-bad-url")
    assert bad_url["outcome"] == "schema_validation"
    assert "sources.0.url" in bad_url["reason"]

    no_sources = _candidate(audit, "agentic_and_dev", "agentic-no-sources")
    assert no_sources["outcome"] == "missing_sources"
    assert no_sources["source_urls"] == []
    assert no_sources["reason"] == "Discovery returned no sources for this candidate."

    repeat = _candidate(audit, "open_source_and_global", "open-repeat")
    assert repeat["outcome"] == "historical_url_match"
    assert HISTORICAL_URL in repeat["reason"]

    assert _candidate(audit, "agentic_and_dev", "agentic-good")["outcome"] == "selected"
    assert _candidate(audit, "open_source_and_global", "open-new")["outcome"] == "selected"
    assert _candidate(audit, "multimodal_and_creative", "multimodal_and_creative-0")["outcome"] == "not_selected"

    safety = _candidate(audit, SAFETY_TRACK, SLOWDOWN_STORY["id"])
    assert safety["outcome"] == "priority_included"
    assert safety["source_urls"] == ["https://www.anthropic.com/news/joint-statement"]

    # Every discovered candidate reached a final, explainable outcome.
    for track in audit["tracks"]:
        for candidate in track["candidates"]:
            assert candidate["outcome"] != "pending", f"{track['track']}:{candidate['id']} has no outcome"
            if candidate["outcome"] not in {"selected", "priority_included"}:
                assert candidate["reason"]
        expected_rejections = [c for c in track["candidates"] if c["outcome"] not in {"selected", "priority_included"}]
        assert track["rejections"] == expected_rejections


def test_audit_records_pool_deduplication_and_selection(completed_audit):
    audit, news_data = completed_audit

    assert audit["pool_accepted_count"] == 10
    assert audit["deduplication"] == {
        "history_editions_loaded": 1,
        "input_count": 10,
        "removed_count": 1,
        "reverted_to_raw": False,
    }

    selection = audit["selection"]
    assert selection["candidate_count"] == 9
    assert selection["fallback_used"] is False
    assert [(a["model"], a["status"]) for a in selection["attempts"]] == [(GEMINI_RESEARCH_MODEL, "success")]
    assert [c["candidate_id"] for c in selection["flagged_priority_candidates"]] == [SLOWDOWN_STORY["id"]]
    assert selection["priority_guard"]["included_ids"] == [SLOWDOWN_STORY["id"]]
    assert selection["selected_ids"] == [item["id"] for item in news_data["items"]]
    assert SLOWDOWN_STORY["id"] in selection["selected_ids"]


def test_audit_records_selection_fallback(research_env):
    def failing_selection(model, prompt, attempt):
        raise RuntimeError("503 UNAVAILABLE")

    research_env.install_client(FakeGenAIClient(_discovery_handler, failing_selection))
    researcher.research_ai_news(EDITION_DATE)
    audit = _load_audit(research_env)

    selection = audit["selection"]
    assert selection["fallback_used"] is True
    assert all(a["status"] == "error" and "503" in a["error"] for a in selection["attempts"])
    selected = [c for t in audit["tracks"] for c in t["candidates"] if c["outcome"] == "selected"]
    assert len(selected) == 4
    assert all(c["reason"] == "Chosen by automated fallback selection." for c in selected)


def test_audit_marked_failed_when_discovery_finds_nothing(research_env):
    def always_failing(track, model, attempt, prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    research_env.install_client(FakeGenAIClient(always_failing, _select_without_safety_story))

    with pytest.raises(RuntimeError, match="no valid candidates"):
        researcher.research_ai_news(EDITION_DATE)

    audit = _load_audit(research_env)
    assert audit["status"] == "failed"
    assert "no valid candidates" in audit["error"]
    assert audit["selection"] is None
    assert len(audit["tracks"]) == len(RESEARCH_TRACKS)
    for track in audit["tracks"]:
        assert track["status"] == "failed"
        assert [a["status"] for a in track["attempts"]] == ["error", "error", "error"]
        assert all("429" in a["error"] for a in track["attempts"])
