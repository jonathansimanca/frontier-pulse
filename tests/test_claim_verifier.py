"""Tests for factual-accuracy prompt rules and the single edition claim check."""

import json
from pathlib import Path
from types import SimpleNamespace

import src.ia_news_researcher as researcher
from conftest import FakeGenAIClient, candidates_from_selection_prompt, discovery_response, selection_response
from src.claim_verifier import apply_claim_corrections, build_claim_check_prompt, verify_edition_claims
from src.config import RESEARCH_TRACKS
from src.ia_news_researcher import build_selection_prompt, build_track_discovery_prompt
from src.research_audit import AUDIT_FILENAME
from src.schemas import Edition
from src.script_generator import build_spanish_prompt

FIXTURES = Path(__file__).parent / "fixtures"
PROBE = json.loads((FIXTURES / "discovery_probe_2026-09-14_run2.json").read_text(encoding="utf-8"))
OVERSTATED_STORY = PROBE["tracks"]["frontier_safety_and_governance"]["items"][0]

CORRECTED_SUMMARY = (
    "Anthropic CEO Dario Amodei published an essay proposing that frontier labs pace capability advances "
    "so safety evaluations can keep up, and committed Anthropic to embedded third-party evaluators. "
    "OpenAI CEO Sam Altman and xAI's Elon Musk publicly agreed with the proposal."
)


def _edition(items):
    scored = [dict(item, relevance_score=5, evidence_score=4, selection_reason="Selected.") for item in items]
    return json.loads(Edition.model_validate({
        "edition_date": "2026-09-14",
        "start_date": "2026-09-07T00:00:00-05:00",
        "end_date": "2026-09-14T23:59:59-05:00",
        "title": "Frontier Pulse - Edition 2026-09-14",
        "is_slow_week": False,
        "items": scored,
    }).model_dump_json())


def _other_story():
    return {
        "id": "openai-agents-api",
        "title": "OpenAI Releases Agents API in Public Beta",
        "category": "Agents",
        "summary": "OpenAI released an Agents API in public beta.",
        "why_it_matters": "Developers can build hosted agents.",
        "key_takeaways": ["Public beta"],
        "sources": [{"title": "OpenAI", "url": "https://openai.com/index/agents-api", "published_date": "2026-09-10"}],
    }


def _response(payload, queries=("amodei pace the frontier altman endorsement",)):
    metadata = SimpleNamespace(web_search_queries=list(queries), grounding_chunks=[])
    return SimpleNamespace(text="```json\n" + json.dumps(payload) + "\n```", candidates=[SimpleNamespace(grounding_metadata=metadata)])


class _Client:
    def __init__(self, handler):
        self.prompts = []
        self.models = SimpleNamespace(generate_content=self._generate)
        self._handler = handler

    def _generate(self, model, contents, config):
        self.prompts.append((model, contents, config))
        return self._handler()


# --- Prompt rules ---------------------------------------------------------------------


def test_fixture_story_names_lab_leaders_whose_endorsements_need_checking():
    # Musk's endorsement was later confirmed by CNBC, CNN and Quartz; Hassabis's was not found.
    assert "Demis Hassabis" in OVERSTATED_STORY["summary"]
    assert "Elon Musk" in OVERSTATED_STORY["summary"]


def test_discovery_prompt_requires_source_faithful_attribution():
    prompt = build_track_discovery_prompt(
        "frontier_safety_and_governance", RESEARCH_TRACKS["frontier_safety_and_governance"], [],
        "2026-09-14", "September 07, 2026 to September 14, 2026", "2026-09-07T00:00:00-05:00", "2026-09-14T23:59:59-05:00",
    )
    assert "FACTUAL ACCURACY RULES:" in prompt
    assert "ONLY when a cited source reports that exact person or organization making it" in prompt
    assert "Never extend one leader's or lab's position to other leaders or labs." in prompt
    assert "Never invent quotes, figures, dates, names, or URLs." in prompt


def test_selection_prompt_keeps_stories_faithful_to_candidates():
    prompt = build_selection_prompt([OVERSTATED_STORY], [], "2026-09-14", "2026-09-07T00:00:00-05:00", "2026-09-14T23:59:59-05:00")
    assert "do not add people, endorsements, commitments, figures, or dates that the candidate does not contain" in prompt


def test_script_prompt_forbids_new_facts_and_requires_attribution():
    prompt = build_spanish_prompt({"edition_date": "2026-09-14", "items": [OVERSTATED_STORY]})
    assert "REGLAS DE PRECISIÓN FACTUAL:" in prompt
    assert "No agregues personas, respaldos, compromisos, citas, cifras, fechas ni benchmarks" in prompt
    assert "Nunca extiendas la postura de una persona o empresa a otras." in prompt


def test_claim_check_prompt_lists_every_story_with_sources():
    edition = _edition([OVERSTATED_STORY, _other_story()])
    prompt = build_claim_check_prompt(edition)
    assert "FACT-CHECK EDITOR" in prompt
    assert "Correct or remove a claim ONLY when a source you found contradicts it" in prompt
    assert "Do NOT remove a claim just because you could not find it." in prompt
    assert '"evidence_url"' in prompt
    for item in edition["items"]:
        assert f'"id": "{item["id"]}"' in prompt
        assert item["sources"][0]["url"] in prompt


# --- Applying corrections -------------------------------------------------------------


def test_corrected_story_replaces_only_text_fields():
    edition = _edition([OVERSTATED_STORY, _other_story()])
    payload = {"items": [
        {
            "id": OVERSTATED_STORY["id"],
            "verdict": "corrected",
            "summary": CORRECTED_SUMMARY,
            "removed_claims": [
                {"claim": "Demis Hassabis endorsed the proposal", "evidence_url": "https://www.cnbc.com/2026/09/14/sam-altman-ai-slowdown-anthropic-amodei-musk.html"},
            ],
        },
        {"id": "openai-agents-api", "verdict": "supported"},
        {"id": "unknown-story", "verdict": "corrected", "summary": "Should be ignored."},
    ]}

    result, records, ignored = apply_claim_corrections(edition, payload)

    corrected = result["items"][0]
    assert corrected["summary"] == CORRECTED_SUMMARY
    assert "Hassabis" not in corrected["summary"]
    for field in ("id", "title", "why_it_matters", "key_takeaways", "sources", "relevance_score", "evidence_score", "selection_reason"):
        assert corrected[field] == edition["items"][0][field]
    assert result["items"][1] == edition["items"][1]
    assert edition["items"][0]["summary"] == OVERSTATED_STORY["summary"], "Input edition must not be mutated"

    assert records == [
        {"id": OVERSTATED_STORY["id"], "verdict": "corrected", "changed_fields": ["summary"],
         "removed_claims": [{"claim": "Demis Hassabis endorsed the proposal",
                             "evidence_url": "https://www.cnbc.com/2026/09/14/sam-altman-ai-slowdown-anthropic-amodei-musk.html"}], "note": None},
        {"id": "openai-agents-api", "verdict": "supported", "changed_fields": [], "removed_claims": [], "note": None},
    ]
    assert ignored == ["unknown-story"]


def test_invalid_correction_keeps_original_text():
    edition = _edition([OVERSTATED_STORY])
    payload = {"items": [{"id": OVERSTATED_STORY["id"], "verdict": "corrected", "summary": "Fixed.", "key_takeaways": [],
                          "removed_claims": [{"claim": "x", "evidence_url": "https://example.com/e"}]}]}

    result, records, _ = apply_claim_corrections(edition, payload)

    assert result["items"][0] == edition["items"][0]
    assert records[0]["verdict"] == "invalid_correction"
    assert "key_takeaways" in records[0]["note"]


def test_story_missing_from_payload_is_not_checked():
    edition = _edition([OVERSTATED_STORY])
    result, records, _ = apply_claim_corrections(edition, {"items": []})
    assert result["items"] == edition["items"]
    assert records[0]["verdict"] == "not_checked"


# --- Running the check ----------------------------------------------------------------


def test_verify_edition_claims_uses_one_grounded_call_and_returns_valid_edition():
    edition = _edition([OVERSTATED_STORY, _other_story()])
    client = _Client(lambda: _response({"items": [
        {"id": OVERSTATED_STORY["id"], "verdict": "corrected", "summary": CORRECTED_SUMMARY,
         "removed_claims": [{"claim": "Hassabis endorsed", "evidence_url": "https://www.cnn.com/2026/09/14/ai-slowdown"}]},
    ]}))

    result, record = verify_edition_claims(client, edition, "gemini-test")

    assert len(client.prompts) == 1
    _, _, config = client.prompts[0]
    assert config.tools and config.tools[0].google_search is not None
    Edition.model_validate(result)
    assert result["items"][0]["summary"] == CORRECTED_SUMMARY
    assert record["status"] == "success"
    assert record["grounded"] is True
    assert record["web_search_queries"] == ["amodei pace the frontier altman endorsement"]
    assert [r["verdict"] for r in record["items"]] == ["corrected", "not_checked"]


def test_verify_edition_claims_keeps_original_on_api_error():
    edition = _edition([OVERSTATED_STORY])

    def failing():
        raise RuntimeError("503 UNAVAILABLE")

    result, record = verify_edition_claims(_Client(failing), edition, "gemini-test")

    assert result == edition
    assert record["status"] == "error"
    assert "503 UNAVAILABLE" in record["error"]


def test_verify_edition_claims_keeps_original_on_unparseable_output():
    edition = _edition([OVERSTATED_STORY])
    grounded_metadata = SimpleNamespace(web_search_queries=["q"], grounding_chunks=[])
    client = _Client(lambda: SimpleNamespace(text="I checked everything, it looks fine.", candidates=[SimpleNamespace(grounding_metadata=grounded_metadata)]))

    result, record = verify_edition_claims(client, edition, "gemini-test")

    assert result == edition
    assert record["status"] == "error"


def test_verify_edition_claims_can_be_disabled():
    edition = _edition([OVERSTATED_STORY])
    client = _Client(lambda: _response({"items": []}))

    result, record = verify_edition_claims(client, edition, "gemini-test", enabled=False)

    assert result == edition
    assert client.prompts == []
    assert record["status"] == "skipped"


# --- Pipeline integration -------------------------------------------------------------


def test_research_pipeline_applies_claim_check_and_records_it(research_env):
    def discovery(track, model, attempt, prompt):
        items = [OVERSTATED_STORY] if track == "frontier_safety_and_governance" else []
        if track == "frontier_labs":
            items = [_other_story()]
        return discovery_response(items, queries=(f"{track} search",))

    def editor(model, prompt, attempt):
        candidates = candidates_from_selection_prompt(prompt)
        return selection_response(candidates, [c["id"] for c in candidates])

    def claim_check(model, prompt):
        assert OVERSTATED_STORY["id"] in prompt
        return _response({"items": [
            {"id": OVERSTATED_STORY["id"], "verdict": "corrected", "summary": CORRECTED_SUMMARY,
             "removed_claims": [{"claim": "Demis Hassabis endorsed the proposal", "evidence_url": "https://www.cnbc.com/2026/09/14/ai-slowdown"}]},
            {"id": "openai-agents-api", "verdict": "supported"},
        ]})

    client = research_env.install_client(FakeGenAIClient(discovery, editor, claim_check))
    news_data = researcher.research_ai_news("2026-09-14")

    assert len(client.models.claim_check_prompts) == 1
    story = next(i for i in news_data["items"] if i["id"] == OVERSTATED_STORY["id"])
    assert story["summary"] == CORRECTED_SUMMARY

    saved = json.loads((research_env.edition_dir("2026-09-14") / "edition.json").read_text(encoding="utf-8"))
    assert next(i for i in saved["items"] if i["id"] == OVERSTATED_STORY["id"])["summary"] == CORRECTED_SUMMARY

    audit = json.loads((research_env.edition_dir("2026-09-14") / AUDIT_FILENAME).read_text(encoding="utf-8"))
    claim_audit = audit["claim_check"]
    assert claim_audit["status"] == "success"
    corrected = next(i for i in claim_audit["items"] if i["id"] == OVERSTATED_STORY["id"])
    assert corrected["verdict"] == "corrected"
    assert corrected["changed_fields"] == ["summary"]
    assert corrected["removed_claims"] == [{"claim": "Demis Hassabis endorsed the proposal", "evidence_url": "https://www.cnbc.com/2026/09/14/ai-slowdown"}]


def test_research_pipeline_continues_when_claim_check_fails(research_env):
    def discovery(track, model, attempt, prompt):
        return discovery_response([OVERSTATED_STORY] if track == "frontier_safety_and_governance" else [])

    def editor(model, prompt, attempt):
        candidates = candidates_from_selection_prompt(prompt)
        return selection_response(candidates, [c["id"] for c in candidates])

    def failing_claim_check(model, prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    research_env.install_client(FakeGenAIClient(discovery, editor, failing_claim_check))
    news_data = researcher.research_ai_news("2026-09-14")

    assert news_data["items"][0]["summary"] == OVERSTATED_STORY["summary"]
    audit = json.loads((research_env.edition_dir("2026-09-14") / AUDIT_FILENAME).read_text(encoding="utf-8"))
    assert audit["status"] == "completed"
    assert audit["claim_check"]["status"] == "error"


# --- Safeguards: grounding and contradiction evidence ---------------------------------


def test_ungrounded_claim_check_applies_no_corrections():
    """2026-09-15: the claim check returned 'supported' for every story without running a search."""
    edition = _edition([OVERSTATED_STORY, _other_story()])
    payload = {"items": [{"id": OVERSTATED_STORY["id"], "verdict": "corrected", "summary": CORRECTED_SUMMARY,
                          "removed_claims": [{"claim": "Musk endorsed", "evidence_url": "https://example.com/e"}]}]}
    client = _Client(lambda: _response(payload, queries=()))

    result, record = verify_edition_claims(client, edition, "gemini-test")

    assert result == edition
    assert record["status"] == "unverified_no_search"
    assert record["grounded"] is False
    assert [r["verdict"] for r in record["items"]] == ["unverified_no_search", "unverified_no_search"]
    assert all(r["changed_fields"] == [] for r in record["items"])


def test_correction_without_evidence_is_rejected():
    edition = _edition([OVERSTATED_STORY])
    for removed in ([], ["Elon Musk endorsed the proposal"], [{"claim": "Elon Musk endorsed the proposal"}],
                    [{"claim": "Elon Musk endorsed the proposal", "evidence_url": "not a url"}]):
        payload = {"items": [{"id": OVERSTATED_STORY["id"], "verdict": "corrected", "summary": CORRECTED_SUMMARY, "removed_claims": removed}]}

        result, records, _ = apply_claim_corrections(edition, payload)

        assert result["items"][0]["summary"] == OVERSTATED_STORY["summary"], removed
        assert records[0]["verdict"] == "invalid_correction"
        assert records[0]["removed_claims"] == []
        assert "evidence" in records[0]["note"] or "removed claim" in records[0]["note"]


def test_true_claims_are_kept_when_the_checker_only_failed_to_find_them():
    """Musk's endorsement was real (reported by CNBC, CNN, Quartz); 'not found' must not remove it."""
    edition = _edition([OVERSTATED_STORY])
    client = _Client(lambda: _response({"items": [{"id": OVERSTATED_STORY["id"], "verdict": "supported"}]}))

    result, record = verify_edition_claims(client, edition, "gemini-test")

    assert "Elon Musk" in result["items"][0]["summary"]
    assert record["items"][0]["verdict"] == "supported"


def test_claim_check_repairs_corrupted_json_and_records_parse_diagnostics():
    edition = _edition([OVERSTATED_STORY])
    raw = (
        '```json\n{\n  "items": [\n    {\n      "id": "' + OVERSTATED_STORY["id"] + '",\n'
        '      "verdict": "corrected",\n'
        '      "key_takeaways":.",\n'
        '        "Amodei proposed pacing frontier AI development."\n'
        '      ],\n'
        '      "removed_claims": [{"claim": "Hassabis endorsed", "evidence_url": "https://www.cnbc.com/2026/09/14/ai-slowdown"}]\n'
        '    }\n  ]\n}\n```'
    )
    metadata = SimpleNamespace(web_search_queries=["q"], grounding_chunks=[])
    client = _Client(lambda: SimpleNamespace(text=raw, candidates=[SimpleNamespace(grounding_metadata=metadata)]))

    result, record = verify_edition_claims(client, edition, "gemini-test")

    assert result["items"][0]["key_takeaways"] == ["Amodei proposed pacing frontier AI development."]
    assert record["status"] == "success"
    assert (record["parse_strategy"], record["parse_repairs"]) == ("repaired", 1)
    assert record["raw_response"] == raw
