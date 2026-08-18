import pytest
from src.quality_gate import validate_edition_quality


@pytest.fixture
def base_valid_edition():
    return {
        "edition_date": "2026-08-03",
        "start_date": "2026-07-27T00:00:00-05:00",
        "end_date": "2026-08-03T23:59:59-05:00",
        "is_slow_week": False,
        "items": [
            {
                "id": "gemini-flash-update",
                "title": "Google release Gemini 2.5 Flash optimizations",
                "category": "LLMs",
                "summary": "Google released incredible performance optimizations for Gemini 2.5 Flash.",
                "why_it_matters": "Improves execution speed for agentic workflows.",
                "key_takeaways": ["2x faster latency", "Reduced cost by 30%"],
                "relevance_score": 5,
                "evidence_score": 5,
                "sources": [
                    {
                        "title": "Google Developers Blog",
                        "url": "https://developers.googleblog.com/gemini-flash-update",
                        "publisher": "Google",
                        "published_date": "2026-08-01"
                    }
                ]
            },
            {
                "id": "claude-agentic-tool",
                "title": "Anthropic launches Claude Computer Use Tool",
                "category": "Agents",
                "summary": "Anthropic releases Claude API integrations allowing direct computer operation.",
                "why_it_matters": "Enables end-to-end automation of desktop tasks.",
                "key_takeaways": ["API integration available", "High desktop accuracy"],
                "relevance_score": 4,
                "evidence_score": 5,
                "sources": [
                    {
                        "title": "Anthropic News",
                        "url": "https://anthropic.com/news/computer-use",
                        "publisher": "Anthropic",
                        "published_date": "2026-07-30"
                    }
                ]
            },
            {
                "id": "llama-os-release",
                "title": "Meta publishes Llama 3.1 405B model",
                "category": "Open Source",
                "summary": "Meta releases weights for their largest open weights model to date.",
                "why_it_matters": "Provides a high-quality alternative to proprietary frontier systems.",
                "key_takeaways": ["405B parameters", "Open weights licensing"],
                "relevance_score": 5,
                "evidence_score": 4,
                "sources": [
                    {
                        "title": "Meta AI Blog",
                        "url": "https://meta.com/blog/llama-os",
                        "publisher": "Meta",
                        "published_date": "2026-07-28"
                    }
                ]
            }
        ]
    }


def test_quality_gate_passed(base_valid_edition):
    """Verify that a perfect, complete and diverse edition passes all quality checks successfully."""
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is True
    assert len(report.reasons_for_failure) == 0
    assert len(report.checks) == 5
    
    # Check individual check marks
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["temporal_alignment"] is True
    assert checks_dict["evidence_grounding"] is True
    assert checks_dict["quality_scoring"] is True
    assert checks_dict["topic_diversity"] is True
    assert checks_dict["slow_week_adjustment"] is True


def test_quality_gate_failed_temporal(base_valid_edition):
    """Verify that an edition fails if majority of sources fall outside the coverage window."""
    # Modify publication dates to be out of the window (start: 2026-07-27, end: 2026-08-03)
    base_valid_edition["items"][0]["sources"][0]["published_date"] = "2026-06-01"
    base_valid_edition["items"][1]["sources"][0]["published_date"] = "2026-06-02"
    
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is False
    assert any("Temporal Alignment" in reason for reason in report.reasons_for_failure)
    
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["temporal_alignment"] is False


def test_quality_gate_failed_grounding(base_valid_edition):
    """Verify that validation fails if source URLs are empty or invalid."""
    base_valid_edition["items"][0]["sources"][0]["url"] = ""
    base_valid_edition["items"][1]["sources"][0]["url"] = "ftp://invalid-scheme"
    
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is False
    assert any("Evidence Grounding" in reason for reason in report.reasons_for_failure)
    
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["evidence_grounding"] is False


def test_quality_gate_failed_diversity(base_valid_edition):
    """Verify that an edition fails if dominated by multiple variants of the same provider/brand."""
    # Change all items to be about OpenAI
    base_valid_edition["items"][0]["title"] = "OpenAI launches GPT-5 search"
    base_valid_edition["items"][0]["summary"] = "OpenAI releases new search platform."
    
    base_valid_edition["items"][1]["title"] = "OpenAI updates ChatGPT Plus features"
    base_valid_edition["items"][1]["summary"] = "OpenAI adds voice tools to ChatGPT."
    
    base_valid_edition["items"][2]["title"] = "OpenAI fine-tuning endpoint releases"
    base_valid_edition["items"][2]["summary"] = "OpenAI releases custom weights."
    
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is False
    assert any("Topic Diversity" in reason for reason in report.reasons_for_failure)
    
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["topic_diversity"] is False


def test_quality_gate_slow_week_adjustment(base_valid_edition):
    """Verify size limits under normal and slow weeks:
    
    - 2 items without slow_week: Fail.
    - 2 items with slow_week: Pass.
    """
    # Slice to 2 items
    base_valid_edition["items"] = base_valid_edition["items"][:2]
    
    # 1. Normal week (slow_week = False) -> Should fail slow_week check
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is False
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["slow_week_adjustment"] is False
    
    # 2. Slow week (slow_week = True) -> Should pass slow_week check
    base_valid_edition["is_slow_week"] = True
    report_slow = validate_edition_quality(base_valid_edition)
    assert report_slow.passed is True
    checks_dict_slow = {c.check_name: c.passed for c in report_slow.checks}
    assert checks_dict_slow["slow_week_adjustment"] is True


def test_quality_gate_failed_blocked_domain(base_valid_edition):
    """Verify that an edition fails if it contains sources from blocked/unreliable domains."""
    base_valid_edition["items"][0]["sources"][0]["url"] = "https://www.facebook.com/story.php?id=12345"
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is False
    assert any("Domain Quality" in reason for reason in report.reasons_for_failure)
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["evidence_grounding"] is False


def test_quality_gate_failed_platform_duplication(base_valid_edition):
    """Verify that an edition fails if multiple stories rely on the same low-quality domain."""
    base_valid_edition["items"][0]["sources"][0]["url"] = "https://capitalbench.com/report1"
    base_valid_edition["items"][1]["sources"][0]["url"] = "https://capitalbench.com/report2"
    report = validate_edition_quality(base_valid_edition)
    assert report.passed is False
    checks_dict = {c.check_name: c.passed for c in report.checks}
    assert checks_dict["evidence_grounding"] is False or checks_dict["topic_diversity"] is False
