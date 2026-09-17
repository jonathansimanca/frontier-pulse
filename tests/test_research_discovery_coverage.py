"""Regression tests for research discovery coverage and candidate-pool construction.

Context: the 2026-09-14 run completed without errors but never discovered a high-impact
story about multiple frontier-lab leaders calling for a slower pace of frontier AI
development. No research track searched for coordinated lab actions, slowdowns,
capability limits, risk thresholds, independent evaluations, or international safety
coordination. These tests keep that vocabulary in the discovery prompts.

The expected terms are written literally here (not imported from config) so that
removing them from the configuration makes these tests fail.
"""

import re

import pytest

from src.config import (
    MAX_CANDIDATES_PER_TRACK,
    MAX_DISCOVERY_POOL_SIZE,
    RESEARCH_TRACKS,
    TRACK_DISCOVERY_FOCUS,
)
from src.ia_news_researcher import (
    build_candidate_pool,
    build_track_discovery_prompt,
    format_search_period,
    scope_query_to_period,
)
from src.schemas import DiscoveryEdition, NewsItem

SAFETY_TRACK = "frontier_safety_and_governance"

# Each concept must be matched by at least one of its patterns in the track queries.
REQUIRED_SAFETY_GOVERNANCE_CONCEPTS = {
    "development pace (slowdown/pause/halt)": [r"\bslowdown\b", r"\bpause\b", r"\bhalt\b", r"\bmoratorium\b"],
    "capability limits": [r"\bcapability limits?\b"],
    "coordinated lab action": [r"\bcoordinated\b", r"\bjoint statement\b"],
    "frontier-model risk thresholds": [r"\brisk thresholds?\b"],
    "catastrophic-risk warnings": [r"\bcatastrophic risk\b"],
    "independent safety evaluations": [r"\bindependent\b.*\bevaluations?\b"],
    "embedded external evaluators": [r"\bexternal evaluators?\b"],
    "safety commitments": [r"\bsafety commitments?\b"],
    "international agreements": [r"\binternational\b.*\bagreements?\b"],
    "public statements by lab leaders": [r"\bleaders\b.*\bstatement\b"],
}

FRONTIER_LAB_PATTERNS = {
    "anthropic": r"\banthropic\b",
    "openai": r"\bopenai\b",
    "xai": r"\bxai\b",
    "google_deepmind": r"\bgoogle deepmind\b",
}

PROMPT_ARGS = {
    "previous_topics": [],
    "edition_date": "2026-09-14",
    "human_window": "September 07, 2026 to September 14, 2026",
    "start_date": "2026-09-07T00:00:00-05:00",
    "end_date": "2026-09-14T23:59:59-05:00",
}


def _labs_in(text: str) -> set[str]:
    lowered = text.lower()
    return {lab for lab, pattern in FRONTIER_LAB_PATTERNS.items() if re.search(pattern, lowered)}


def _build_prompt(track_key: str) -> str:
    return build_track_discovery_prompt(track_key, RESEARCH_TRACKS[track_key], **PROMPT_ARGS)


def _make_item(item_id: str, title: str, url: str = "https://example.com/story") -> dict:
    return {
        "id": item_id,
        "title": title,
        "category": "Test",
        "summary": "A factual summary of the development.",
        "why_it_matters": "It matters for frontier AI.",
        "key_takeaways": ["Takeaway"],
        "sources": [{"title": "Source", "url": url, "publisher": "Publisher", "published_date": "2026-09-10"}],
    }


# --- Test 1: discovery prompts cover frontier AI safety and governance ---------------


def test_safety_and_governance_track_is_configured():
    assert SAFETY_TRACK in RESEARCH_TRACKS
    assert len(RESEARCH_TRACKS[SAFETY_TRACK]) >= 5


@pytest.mark.parametrize("concept", sorted(REQUIRED_SAFETY_GOVERNANCE_CONCEPTS))
def test_safety_track_queries_cover_required_vocabulary(concept):
    queries_text = "\n".join(RESEARCH_TRACKS[SAFETY_TRACK]).lower()
    patterns = REQUIRED_SAFETY_GOVERNANCE_CONCEPTS[concept]
    assert any(re.search(p, queries_text) for p in patterns), (
        f"No '{SAFETY_TRACK}' query covers the concept '{concept}' (patterns: {patterns})"
    )


def test_safety_track_queries_combine_frontier_labs():
    queries = RESEARCH_TRACKS[SAFETY_TRACK]

    # The track as a whole names every major frontier lab.
    assert _labs_in(" ".join(queries)) == set(FRONTIER_LAB_PATTERNS)

    # At least one query combines Anthropic, OpenAI and xAI (the 2026-09-14 miss).
    assert any({"anthropic", "openai", "xai"} <= _labs_in(q) for q in queries)

    # Coordination queries must name multiple labs together, not one lab at a time.
    multi_lab_queries = [q for q in queries if len(_labs_in(q)) >= 3]
    assert len(multi_lab_queries) >= 2


def test_safety_track_prompt_includes_focus_queries_and_vocabulary():
    prompt = _build_prompt(SAFETY_TRACK)
    prompt_lower = prompt.lower()

    assert "TRACK FOCUS:" in prompt
    for query in RESEARCH_TRACKS[SAFETY_TRACK]:
        assert f"- {query}" in prompt

    for term in [
        "multiple frontier labs",
        "slowdown",
        "pause",
        "capability limits",
        "risk thresholds",
        "catastrophic-risk warnings",
        "independent or embedded external",
        "voluntary safety commitments",
        "international ai safety agreements",
    ]:
        assert term in prompt_lower, f"Safety track prompt is missing '{term}'"


def test_discovery_prompt_no_longer_forces_product_launch_framing():
    prompt = _build_prompt(SAFETY_TRACK)
    assert "Search actively for major official announcements, model releases" not in prompt
    assert "Minor standards updates or speculative blog posts." not in prompt


@pytest.mark.parametrize("track_key", sorted(RESEARCH_TRACKS))
def test_every_prompt_treats_on_record_statements_as_substantive(track_key):
    prompt = _build_prompt(track_key)
    assert "On-the-record public statements" in prompt
    assert "not speculation" in prompt


def test_every_track_has_its_own_discovery_focus():
    assert set(RESEARCH_TRACKS) <= set(TRACK_DISCOVERY_FOCUS)
    focuses = [TRACK_DISCOVERY_FOCUS[key] for key in RESEARCH_TRACKS]
    assert len(set(focuses)) == len(focuses)

    safety_prompt = _build_prompt(SAFETY_TRACK)
    labs_prompt = _build_prompt("frontier_labs")
    assert TRACK_DISCOVERY_FOCUS[SAFETY_TRACK] in safety_prompt
    assert TRACK_DISCOVERY_FOCUS[SAFETY_TRACK] not in labs_prompt


def test_frontier_labs_queries_do_not_pin_stale_model_versions():
    queries_text = " ".join(RESEARCH_TRACKS["frontier_labs"])
    for stale in [r"\bo1\b", r"\bo3\b", r"\bV3\b", r"\bR1\b", r"Sonnet Opus Haiku"]:
        assert not re.search(stale, queries_text), f"frontier_labs queries still pin '{stale}'"


# --- Candidate pool construction ------------------------------------------------------


def test_pool_size_constant_matches_discovery_schema():
    items_field = DiscoveryEdition.model_fields["items"]
    max_lengths = [m.max_length for m in items_field.metadata if hasattr(m, "max_length")]
    assert max_lengths == [MAX_DISCOVERY_POOL_SIZE]


def test_full_discovery_pool_is_capped_without_starving_the_last_track():
    track_results = [
        (track_key, [_make_item(f"{track_key}-{i}", f"{track_key} story {i}") for i in range(MAX_CANDIDATES_PER_TRACK)])
        for track_key in RESEARCH_TRACKS
    ]
    total = sum(len(items) for _, items in track_results)
    assert total > MAX_DISCOVERY_POOL_SIZE, "Precondition: a full run must exceed the pool cap"

    accepted, rejections = build_candidate_pool(track_results)

    assert len(accepted) == MAX_DISCOVERY_POOL_SIZE
    assert len(rejections) == total - MAX_DISCOVERY_POOL_SIZE
    assert all(r["stage"] == "pool_size_cap" for r in rejections)

    # Every track keeps most of its candidates, including the safety track that runs last.
    per_track = {key: sum(1 for item in accepted if item["id"].startswith(f"{key}-")) for key in RESEARCH_TRACKS}
    assert min(per_track.values()) >= MAX_DISCOVERY_POOL_SIZE // len(RESEARCH_TRACKS)
    assert per_track[SAFETY_TRACK] >= 1
    # Each track's top-ranked candidate is always kept.
    for key in RESEARCH_TRACKS:
        assert any(item["id"] == f"{key}-0" for item in accepted)

    # The capped pool satisfies the discovery contract.
    DiscoveryEdition.model_validate({"edition_date": "2026-09-14", "items": accepted})


def test_invalid_candidate_is_rejected_without_aborting_the_pool():
    bad_item = _make_item("bad-url", "Story with a broken source URL", url="not-a-url")
    no_takeaways = _make_item("no-takeaways", "Story without takeaways")
    no_takeaways["key_takeaways"] = []
    good_item = _make_item("good", "Frontier labs publish joint safety statement", url="https://anthropic.com/news/x")

    accepted, rejections = build_candidate_pool([("benchmarks_safety_and_policy", [bad_item, no_takeaways]), (SAFETY_TRACK, [good_item])])

    assert [item["id"] for item in accepted] == ["good"]
    assert {r["id"] for r in rejections} == {"bad-url", "no-takeaways"}
    assert all(r["stage"] == "schema_validation" for r in rejections)
    assert all(r["reason"] for r in rejections)
    bad_rejection = next(r for r in rejections if r["id"] == "bad-url")
    assert "sources" in bad_rejection["reason"]
    assert bad_rejection["track"] == "benchmarks_safety_and_policy"

    # Accepted items are normalized, JSON-compatible NewsItem dumps.
    assert isinstance(accepted[0]["sources"][0]["url"], str)
    NewsItem.model_validate(accepted[0])


def test_duplicate_titles_across_tracks_are_rejected_with_reason():
    first = _make_item("labs-version", "Frontier Labs Call For Slower AI Development")
    duplicate = _make_item("safety-version", "  frontier labs call for slower AI development ")

    accepted, rejections = build_candidate_pool([("frontier_labs", [first]), (SAFETY_TRACK, [duplicate])])

    assert [item["id"] for item in accepted] == ["labs-version"]
    assert rejections == [
        {
            "track": SAFETY_TRACK,
            "id": "safety-version",
            "title": "  frontier labs call for slower AI development ",
            "stage": "pool_duplicate_title",
            "reason": "Same title already accepted from an earlier track or rank.",
        }
    ]


def test_empty_track_results_produce_empty_pool():
    assert build_candidate_pool([]) == ([], [])
    assert build_candidate_pool([("frontier_labs", [])]) == ([], [])


# --- Date-anchored searches -----------------------------------------------------------
# The 2026-09-15 production audit showed the safety track searching
# "September 2024 OR September 2025 OR September 2026": grounded search hedged across years.


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("2026-09-08T00:00:00-05:00", "2026-09-15T23:59:59-05:00", "September 2026"),
        ("2026-08-28T00:00:00-05:00", "2026-09-04T23:59:59-05:00", "August September 2026"),
        ("2025-12-29T00:00:00-05:00", "2026-01-05T23:59:59-05:00", "December 2025 January 2026"),
    ],
)
def test_format_search_period(start, end, expected):
    assert format_search_period(start, end) == expected


def test_scope_query_to_period_does_not_duplicate_years():
    assert scope_query_to_period("AI labs slowdown", "September 2026") == "AI labs slowdown September 2026"
    assert scope_query_to_period("EU AI Act 2026 enforcement", "September 2026") == "EU AI Act 2026 enforcement"


@pytest.mark.parametrize("track_key", sorted(RESEARCH_TRACKS))
def test_every_target_query_is_scoped_to_the_coverage_period(track_key):
    prompt = build_track_discovery_prompt(
        track_key, RESEARCH_TRACKS[track_key], [], "2026-09-15",
        "September 08, 2026 to September 15, 2026", "2026-09-08T00:00:00-05:00", "2026-09-15T23:59:59-05:00",
    )
    queries_block = prompt.split("TARGET SEARCH QUERIES TO INVESTIGATE:\n", 1)[1].split("\n\n", 1)[0]
    lines = [line for line in queries_block.splitlines() if line.startswith("- ")]

    assert len(lines) == len(RESEARCH_TRACKS[track_key])
    for line, query in zip(lines, RESEARCH_TRACKS[track_key]):
        assert line == f"- {scope_query_to_period(query, 'September 2026')}"
        assert "2026" in line

    assert "Current Year: 2026" in prompt
    assert "Run each TARGET SEARCH QUERY below as its own Google search" in prompt
    assert "Limit every search, including any additional searches you choose to run, to September 2026. Never add or search earlier years." in prompt
    assert "2024" not in prompt and "2025" not in prompt


# --- Second safety pass: headline-style queries ---------------------------------------
# Long descriptive queries were rewritten by grounded search into generic searches on
# 2026-09-15, missing the widely reported frontier-lab CEO slowdown call.

HEADLINES_TRACK = "frontier_safety_headlines"


def test_headline_safety_pass_is_configured_after_the_main_safety_track():
    tracks = list(RESEARCH_TRACKS)
    assert HEADLINES_TRACK in tracks
    assert tracks.index(HEADLINES_TRACK) == tracks.index(SAFETY_TRACK) + 1


def test_headline_queries_are_short_and_cover_the_event_vocabulary():
    queries = RESEARCH_TRACKS[HEADLINES_TRACK]
    assert len(queries) >= 5
    assert all(len(q.split()) <= 9 for q in queries), queries
    assert set(queries).isdisjoint(RESEARCH_TRACKS[SAFETY_TRACK])

    text = " ".join(queries).lower()
    for pattern in [r"\bslowdown\b|\bslow\b", r"\bpause\b", r"\bceos?\b", r"\bpledge\b|\bcommitments?\b",
                    r"\bagreement\b", r"\bstocks?\b", r"\baltman\b", r"\bamodei\b", r"\bmusk\b", r"\bhassabis\b"]:
        assert re.search(pattern, text), pattern


def test_headline_pass_prompt_uses_its_own_focus_and_scoped_queries():
    prompt = build_track_discovery_prompt(
        HEADLINES_TRACK, RESEARCH_TRACKS[HEADLINES_TRACK], [], "2026-09-15",
        "September 08, 2026 to September 15, 2026", "2026-09-08T00:00:00-05:00", "2026-09-15T23:59:59-05:00",
    )
    assert TRACK_DISCOVERY_FOCUS[HEADLINES_TRACK] in prompt
    assert "- AI CEOs call for AI slowdown September 2026" in prompt
    assert "Report the underlying development, not the market reaction alone" in prompt
