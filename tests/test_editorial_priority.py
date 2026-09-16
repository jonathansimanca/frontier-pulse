"""Tests for editorial prioritization of multi-lab frontier AI safety and governance stories.

Covers:
- Test 2 of the 2026-09-14 remediation: a candidate describing a coordinated slowdown or
  safety commitment by multiple frontier labs is classified as a high-priority story.
- A false-positive regression set built from the real 2026-09-14 discovery pool.
- The selection rubric (Tier 1/2 safety and governance criteria, funding capped at Tier 2).
- The deterministic inclusion guard that adds an omitted flagged story (approved option b).

All story texts below are synthetic fixtures, except tests/fixtures/candidates_2026-09-14.json.
"""

import json
from pathlib import Path

import pytest

from src.editorial_priority import (
    MAX_EDITION_ITEMS,
    PRIORITY_CATEGORY,
    classify_candidates,
    classify_priority,
    enforce_priority_inclusion,
)
from src.ia_news_researcher import apply_priority_inclusion, build_selection_prompt
from src.schemas import Edition

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_candidate(
    item_id: str,
    title: str,
    summary: str = "A factual summary.",
    why: str = "It matters.",
    urls: tuple[str, ...] = ("https://www.reuters.com/technology/story",),
) -> dict:
    return {
        "id": item_id,
        "title": title,
        "category": "AI Safety & Governance",
        "summary": summary,
        "why_it_matters": why,
        "key_takeaways": ["Takeaway"],
        "sources": [
            {"title": f"Source {i}", "url": url, "publisher": "Publisher", "published_date": "2026-09-12"}
            for i, url in enumerate(urls)
        ],
        "relevance_score": None,
        "evidence_score": None,
        "selection_reason": None,
    }


def make_selected(item_id: str, title: str, url: str) -> dict:
    item = make_candidate(item_id, title, urls=(url,))
    item.update(relevance_score=5, evidence_score=5, selection_reason="Selected by model.")
    return item


def make_edition(items: list[dict]) -> dict:
    return {
        "edition_date": "2026-09-14",
        "start_date": "2026-09-07T00:00:00-05:00",
        "end_date": "2026-09-14T23:59:59-05:00",
        "title": "Frontier Pulse - Edition 2026-09-14",
        "is_slow_week": False,
        "items": items,
    }


SLOWDOWN_STORY = make_candidate(
    "frontier-labs-call-for-slower-development",
    "Anthropic, OpenAI and xAI Leaders Call for a Slower Pace of Frontier AI Development",
    summary=(
        "Leaders of Anthropic, OpenAI, and xAI issued a joint statement urging the industry to slow down "
        "frontier AI development until independent safety evaluations can keep pace."
    ),
    why="A coordinated call by competing frontier labs could change the speed and oversight of advanced AI.",
    urls=("https://www.anthropic.com/news/joint-statement", "https://www.reuters.com/technology/labs-slowdown"),
)

COMMITMENT_STORY = make_candidate(
    "labs-sign-safety-commitments",
    "Google DeepMind and Meta Sign Voluntary Safety Commitments on Frontier Model Risk Thresholds",
    summary="Google DeepMind and Meta agreed to shared catastrophic-risk thresholds that would trigger a deployment pause.",
    urls=("https://deepmind.google/discover/blog/commitments",),
)

UNSELECTED_PRODUCT_STORIES = [
    make_selected("qualcomm-amazon", "Amazon and Qualcomm Forge Custom Inference Silicon Partnership", "https://www.unite.ai/a"),
    make_selected("mistral-series-d", "Mistral AI Secures EUR 3 Billion Series D", "https://news.samsung.com/b"),
    make_selected("aws-vllm", "AWS and vLLM Publish Trillion-Parameter Reference Infrastructure", "https://aws.amazon.com/c"),
    make_selected("google-eu-hub", "Google Commits EUR 13 Billion to European AI Hub", "https://www.googlecloudpresscorner.com/d"),
]


# --- Test 2: classification -----------------------------------------------------------


def test_coordinated_slowdown_by_multiple_frontier_labs_is_high_priority():
    signal = classify_priority(SLOWDOWN_STORY)

    assert signal.flagged is True
    assert signal.category == PRIORITY_CATEGORY
    assert {"anthropic", "openai", "xai"} <= set(signal.labs)
    assert "development slowdown" in signal.signals
    assert "joint or coordinated safety action" in signal.signals
    assert "anthropic" in signal.reason


def test_coordinated_safety_commitment_by_multiple_frontier_labs_is_high_priority():
    signal = classify_priority(COMMITMENT_STORY)

    assert signal.flagged is True
    assert set(signal.labs) >= {"google_deepmind", "meta"}
    assert {"joint or coordinated safety action", "frontier risk thresholds"} <= set(signal.signals)


@pytest.mark.parametrize(
    "phrase, expected_signal",
    [
        ("leaders urged a slower pace of development", "development slowdown"),
        ("calls to slow down frontier training", "development slowdown"),
        ("argued that we must pace the frontier", "development slowdown"),
        ("proposed pacing AI development with checkpoints", "development slowdown"),
        ("proposed a pause on training runs", "development pause or halt"),
        ("agreed to halt deployment", "development pause or halt"),
        ("a six-month moratorium", "development pause or halt"),
        ("new capability limits for agents", "capability limits"),
        ("an open letter signed by researchers", "joint or coordinated safety action"),
        ("voluntary commitments on model release", "joint or coordinated safety action"),
        ("shared deployment thresholds", "frontier risk thresholds"),
        ("warned of catastrophic risks", "frontier risk thresholds"),
        ("independent third-party evaluations before launch", "independent safety evaluation"),
        ("embedded external evaluators", "independent safety evaluation"),
        ("pre-deployment testing by the institute", "independent safety evaluation"),
        ("signed an international AI safety agreement", "international safety coordination"),
    ],
)
def test_multi_lab_story_with_each_action_signal_is_flagged(phrase, expected_signal):
    story = make_candidate("signal", "OpenAI and Anthropic Update", summary=f"OpenAI and Anthropic {phrase}.")
    signal = classify_priority(story)
    assert expected_signal in signal.signals
    assert signal.flagged is True


@pytest.mark.parametrize(
    "title, summary",
    [
        ("Microsoft Adds xAI Grok and OpenAI Models to Copilot", "Microsoft integrates Grok and OpenAI models into Office apps."),
        ("Anthropic and OpenAI Cut API Prices for Enterprise Customers", "Both labs announced cheaper tokens and faster inference."),
    ],
)
def test_multi_lab_product_news_is_not_flagged(title, summary):
    signal = classify_priority(make_candidate("product", title, summary=summary))
    assert len(signal.labs) >= 2
    assert signal.flagged is False
    assert signal.reason == "No specific safety/governance action signal."


def test_noun_phrase_pace_of_ai_development_is_not_a_signal():
    story = make_candidate(
        "pace-noun",
        "OpenAI and Google Raise Prices Amid the Rapid Pace of AI Development",
        summary="OpenAI and Google said the rapid pace of AI development requires more compute spending.",
    )
    signal = classify_priority(story)
    assert len(signal.labs) >= 2
    assert signal.signals == []
    assert signal.flagged is False


def test_single_lab_safety_update_is_not_flagged():
    story = make_candidate(
        "single-lab-policy",
        "Anthropic Updates Its Risk Thresholds for Model Deployment",
        summary="Anthropic revised catastrophic-risk thresholds in its responsible scaling policy.",
    )
    signal = classify_priority(story)
    assert signal.labs == ["anthropic"]
    assert signal.signals
    assert signal.flagged is False


def test_regulator_only_action_is_not_flagged():
    story = make_candidate(
        "aisi-framework",
        "UK AI Safety Institute Releases Frontier Model Framework v2",
        summary="The institute mandates independent evaluations and cyber uplift disclosures for frontier developers.",
    )
    assert classify_priority(story).flagged is False


def test_generic_safety_words_do_not_trigger_flag():
    story = make_candidate(
        "generic-safety",
        "OpenAI and Google DeepMind Publish Safety and Evaluation Research on Regulation",
        summary="Both labs released papers about AI safety, model evaluation, alignment, and regulation.",
    )
    signal = classify_priority(story)
    assert len(signal.labs) >= 2
    assert signal.flagged is False


def test_real_2026_09_14_candidate_pool_has_no_false_positives():
    fixture = json.loads((FIXTURES_DIR / "candidates_2026-09-14.json").read_text(encoding="utf-8"))
    candidates = fixture["items"]
    assert len(candidates) == 19

    flagged = [s.title for s in classify_candidates(candidates) if s.flagged]
    assert flagged == []


# --- Selection rubric -----------------------------------------------------------------


def _selection_prompt(priority_signals=None) -> str:
    return build_selection_prompt(
        [SLOWDOWN_STORY],
        [],
        "2026-09-14",
        "2026-09-07T00:00:00-05:00",
        "2026-09-14T23:59:59-05:00",
        priority_signals=priority_signals,
    )


def test_selection_rubric_includes_safety_and_governance_tiers():
    prompt = _selection_prompt()
    tier1 = prompt.split("- TIER 1")[1].split("- TIER 2")[0]
    tier2 = prompt.split("- TIER 2")[1].split("- TIER 3")[0]

    assert "Coordinated safety commitments" in tier1
    assert "multiple frontier AI labs" in tier1
    assert "speed, safety, or oversight of advanced AI" in tier1
    assert "slow down, pause, or limit frontier AI development" in tier1

    assert "safety policies, risk or deployment thresholds, or evaluation requirements" in tier2
    assert "International coordination, regulatory action, or governance agreements" in tier2


def test_selection_rubric_caps_funding_and_partnerships_at_tier_2():
    prompt = _selection_prompt()
    tier1 = prompt.split("- TIER 1")[1].split("- TIER 2")[0]
    tier2 = prompt.split("- TIER 2")[1].split("- TIER 3")[0]

    assert "funding" not in tier1.lower()
    assert "partnership" not in tier1.lower()
    assert "Funding rounds, valuations, and commercial or infrastructure partnerships. These are AT MOST TIER 2 and never Tier 1." in tier2
    assert "must never be ranked below a single-company product launch, funding round, or partnership" in prompt


def test_selection_prompt_lists_flagged_candidates_only_when_present():
    assert "DETERMINISTIC PRIORITY SIGNALS" not in _selection_prompt()
    assert "DETERMINISTIC PRIORITY SIGNALS" not in _selection_prompt([classify_priority(COMMITMENT_STORY).to_dict() | {"flagged": False}])

    prompt = _selection_prompt([classify_priority(SLOWDOWN_STORY).to_dict()])
    assert "DETERMINISTIC PRIORITY SIGNALS" in prompt
    assert "id='frontier-labs-call-for-slower-development'" in prompt
    assert "rank it TIER 1 and select it" in prompt


# --- Inclusion guard (option b) -------------------------------------------------------


def test_guard_appends_omitted_flagged_story_when_edition_has_room():
    edition = make_edition(list(UNSELECTED_PRODUCT_STORIES))
    candidates = list(UNSELECTED_PRODUCT_STORIES) + [SLOWDOWN_STORY]

    result, record = enforce_priority_inclusion(edition, candidates)

    assert len(edition["items"]) == 4, "Input edition must not be mutated"
    assert [item["id"] for item in result["items"][:4]] == [item["id"] for item in UNSELECTED_PRODUCT_STORIES]
    added = result["items"][4]
    assert added["id"] == SLOWDOWN_STORY["id"]
    assert added["relevance_score"] == 5
    assert added["evidence_score"] == 5  # two authoritative sources
    assert added["selection_reason"].startswith("Deterministic priority inclusion")
    assert record["included_ids"] == [SLOWDOWN_STORY["id"]]
    assert record["decisions"][0]["action"] == "included"
    Edition.model_validate(result)


def test_guard_is_noop_when_flagged_story_already_selected_under_rewritten_id():
    rewritten = make_selected(
        "model-rewritten-id",
        "Frontier Labs Urge Slowdown",
        "https://www.reuters.com/technology/labs-slowdown/?utm_source=feed",
    )
    edition = make_edition(UNSELECTED_PRODUCT_STORIES[:3] + [rewritten])

    result, record = enforce_priority_inclusion(edition, [SLOWDOWN_STORY])

    assert result["items"] == edition["items"]
    assert record["included_ids"] == []
    assert record["decisions"][0]["action"] == "already_selected"


def test_guard_never_replaces_stories_when_edition_is_full():
    full = UNSELECTED_PRODUCT_STORIES + [make_selected("fifth", "Fifth Story", "https://techcrunch.com/e")]
    assert len(full) == MAX_EDITION_ITEMS

    result, record = enforce_priority_inclusion(make_edition(full), [SLOWDOWN_STORY])

    assert [i["id"] for i in result["items"]] == [i["id"] for i in full]
    assert record["decisions"][0]["action"] == "skipped_edition_full"


def test_guard_requires_an_authoritative_source():
    unverified = dict(SLOWDOWN_STORY, sources=[{"title": "Blog", "url": "https://random-ai-blog.example/post"}])
    redirect_only = dict(
        SLOWDOWN_STORY,
        id="redirect-only",
        sources=[{"title": "Grounding", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"}],
    )
    edition = make_edition(UNSELECTED_PRODUCT_STORIES[:3])

    result, record = enforce_priority_inclusion(edition, [unverified, redirect_only])

    assert len(result["items"]) == 3
    assert [d["action"] for d in record["decisions"]] == [
        "skipped_no_authoritative_source",
        "skipped_only_grounding_redirect_sources",
    ]


def test_guard_adds_at_most_one_story_and_prefers_more_labs():
    edition = make_edition(UNSELECTED_PRODUCT_STORIES[:2])

    result, record = enforce_priority_inclusion(edition, [COMMITMENT_STORY, SLOWDOWN_STORY])

    assert len(result["items"]) == 3
    assert record["included_ids"] == [SLOWDOWN_STORY["id"]]  # 3 labs beats 2 labs
    actions = {d["candidate_id"]: d["action"] for d in record["decisions"]}
    assert actions[COMMITMENT_STORY["id"]] == "skipped_inclusion_limit_reached"


def test_guard_skips_when_edition_already_has_a_flagged_story_under_different_title_and_urls():
    other_version = make_selected(
        "same-event-other-version",
        "Frontier Lab Leaders Back Coordinated Slowdown After Anthropic Essay",
        "https://www.theguardian.com/technology/other-version",
    )
    other_version["summary"] = "Anthropic, OpenAI and xAI leaders issued a joint statement backing a slowdown."
    assert classify_priority(other_version).flagged
    edition = make_edition(UNSELECTED_PRODUCT_STORIES[:2] + [other_version])

    result, record = enforce_priority_inclusion(edition, [SLOWDOWN_STORY])

    assert result["items"] == edition["items"]
    assert record["included_ids"] == []
    decision = record["decisions"][0]
    assert decision["action"] == "skipped_priority_story_already_selected"
    assert decision["selected_priority_ids"] == ["same-event-other-version"]


def test_guard_ignores_unflagged_omitted_candidates():
    edition = make_edition(UNSELECTED_PRODUCT_STORIES[:2])
    omitted = make_candidate("omitted-product", "OpenAI Launches New Image Model", urls=("https://openai.com/x",))

    result, record = enforce_priority_inclusion(edition, [omitted])

    assert result["items"] == edition["items"]
    assert record == {"category": PRIORITY_CATEGORY, "flagged_count": 0, "included_ids": [], "decisions": []}


def test_apply_priority_inclusion_returns_schema_valid_edition():
    edition = json.loads(Edition.model_validate(make_edition(list(UNSELECTED_PRODUCT_STORIES))).model_dump_json())

    news_data, record = apply_priority_inclusion(edition, list(UNSELECTED_PRODUCT_STORIES) + [SLOWDOWN_STORY])

    assert record["included_ids"] == [SLOWDOWN_STORY["id"]]
    assert len(news_data["items"]) == 5
    assert news_data["items"][4]["sources"][0]["url"] == "https://www.anthropic.com/news/joint-statement"
    Edition.model_validate(news_data)
