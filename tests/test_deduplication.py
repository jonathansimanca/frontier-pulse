import pytest
from src.schemas import NewsItem
from src.ia_news_researcher import deterministic_deduplicate

def make_dummy_news_item(id: str, title: str, urls: list[str]) -> NewsItem:
    """Helper to create dummy NewsItem with specified title and source URLs."""
    return NewsItem.model_validate({
        "id": id,
        "title": title,
        "category": "Test",
        "summary": "This is a dummy test news item.",
        "why_it_matters": "Test context matters.",
        "key_takeaways": ["Takeaway"],
        "sources": [
            {"title": f"Source {i}", "url": url}
            for i, url in enumerate(urls)
        ]
    })

def test_dedup_by_source_url():
    """Verify that candidates with source URLs matching history are filtered out."""
    # Setup historical edition with some URLs
    history = [
        {
            "edition_date": "2026-08-01",
            "items": [
                {
                    "title": "Old Release Story",
                    "sources": [
                        {"title": "OpenAI Blog", "url": "https://blog.openai.com/gpt-5-release/"},
                        {"title": "Aggregator", "url": "https://news.ycombinator.com/item?id=123"}
                    ]
                }
            ]
        }
    ]
    
    # Candidate 1: Direct URL match
    c1 = make_dummy_news_item("gpt-5-again", "Some Title", ["https://blog.openai.com/gpt-5-release/"])
    # Candidate 2: Normalization match (capitalization, query params, trailing slashes)
    c2 = make_dummy_news_item("gpt-5-variant", "Other Title", ["HTTPS://BLOG.OPENAI.COM/GPT-5-RELEASE/?utm_source=news"])
    # Candidate 3: No URL match
    c3 = make_dummy_news_item("claude-next", "Claude 4.5 Release", ["https://anthropic.com/claude-4-5"])
    
    candidates = [c1, c2, c3]
    result = deterministic_deduplicate(candidates, history)
    
    # Only c3 should remain
    assert len(result) == 1
    assert result[0].id == "claude-next"

def test_dedup_by_title_similarity():
    """Verify that candidates with titles highly similar to history are filtered out."""
    history = [
        {
            "edition_date": "2026-08-01",
            "items": [
                {
                    "title": "Anthropic Unveils Claude 4.5 with Complex Agentic Capabilities",
                    "sources": [{"title": "Source", "url": "https://anthropic.com/blog"}]
                }
            ]
        }
    ]
    
    # Candidate 1: Highly similar title (high Jaccard overlap)
    c1 = make_dummy_news_item(
        "claude-similar", 
        "Anthropic Launches Claude 4.5 featuring Advanced Agentic Capabilities", 
        ["https://news.tech.com/claude-45"]
    )
    # Candidate 2: Unrelated title
    c2 = make_dummy_news_item(
        "llama-unrelated", 
        "Meta Releases Llama 3.3 for On-Device Deployment", 
        ["https://meta.com/llama"]
    )
    
    candidates = [c1, c2]
    result = deterministic_deduplicate(candidates, history)
    
    # Only c2 should remain
    assert len(result) == 1
    assert result[0].id == "llama-unrelated"

def test_dedup_empty_history():
    """Verify that deduplication behaves gracefully and preserves all items if history is empty."""
    candidates = [
        make_dummy_news_item("story1", "Story 1", ["https://site1.com"]),
        make_dummy_news_item("story2", "Story 2", ["https://site2.com"])
    ]
    result = deterministic_deduplicate(candidates, [])
    assert len(result) == 2
