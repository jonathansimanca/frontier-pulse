import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from src.schemas import Edition, NewsItem, SourceReference

def test_valid_edition():
    """Test that a valid edition dictionary successfully parses into the Edition model."""
    valid_data = {
        "edition_date": "2026-08-04",
        "title": "Frontier Pulse - Edición 2026-08-04",
        "is_slow_week": False,
        "generation_timestamp": "2026-08-04T19:00:00Z",
        "items": [
            {
                "id": "project-astra-release",
                "title": "Google DeepMind launches Project Astra updates",
                "category": "Agents",
                "summary": "Google launches new capabilities for Project Astra agentic framework with real-time video processing.",
                "why_it_matters": "Astra is a priority project for our technology watch.",
                "key_takeaways": [
                    "Real-time low-latency video and audio processing",
                    "Integration with Gemini 2.5 models"
                ],
                "sources": [
                    {
                        "title": "Project Astra Announcement",
                        "url": "https://deepmind.google/technologies/astra/",
                        "publisher": "Google DeepMind",
                        "published_date": "2026-08-03"
                    }
                ]
            }
        ]
    }
    
    edition = Edition.model_validate(valid_data)
    assert edition.edition_date == "2026-08-04"
    assert len(edition.items) == 1
    assert edition.items[0].id == "project-astra-release"
    assert edition.items[0].sources[0].publisher == "Google DeepMind"

def test_invalid_url_validation():
    """Test that an invalid URL in sources triggers a ValidationError."""
    invalid_data = {
        "edition_date": "2026-08-04",
        "title": "Frontier Pulse - Edición 2026-08-04",
        "is_slow_week": False,
        "items": [
            {
                "id": "project-astra-release",
                "title": "Google DeepMind launches Project Astra updates",
                "category": "Agents",
                "summary": "Google launches new capabilities for Project Astra",
                "why_it_matters": "Test case for URL",
                "key_takeaways": ["Takeaway"],
                "sources": [
                    {
                        "title": "Bad Source",
                        "url": "not-a-valid-url"  # Invalid URL
                    }
                ]
            }
        ]
    }
    with pytest.raises(ValidationError):
        Edition.model_validate(invalid_data)
def test_missing_required_fields():
    """Test that missing required fields trigger a ValidationError."""
    invalid_data = {
        "edition_date": "2026-08-04",
        "title": "Frontier Pulse - Edición 2026-08-04",
        "is_slow_week": False,
        "items": [
            {
                # Missing 'id', 'category', 'summary', 'why_it_matters', etc.
                "title": "Incomplete News Item",
                "key_takeaways": ["Only takeaways"]
            }
        ]
    }
    
    with pytest.raises(ValidationError):
        Edition.model_validate(invalid_data)


def test_empty_lists_validation():
    """Test that empty key_takeaways or sources list triggers a ValidationError."""
    invalid_data = {
        "edition_date": "2026-08-04",
        "title": "Frontier Pulse - Edición 2026-08-04",
        "is_slow_week": False,
        "items": [
            {
                "id": "test-empty-lists",
                "title": "Google DeepMind launches Project Astra updates",
                "category": "Agents",
                "summary": "Google launches new capabilities for Project Astra",
                "why_it_matters": "Test",
                "key_takeaways": [],  # Empty list (violates min_items=1)
                "sources": []         # Empty list (violates min_items=1)
            }
        ]
    }
    
    with pytest.raises(ValidationError):
        Edition.model_validate(invalid_data)

def test_discovery_edition_validation():
    """Test that DiscoveryEdition validates with up to 15 items and correct structure."""
    from src.schemas import DiscoveryEdition
    
    valid_discovery = {
        "edition_date": "2026-08-04",
        "items": [
            {
                "id": f"story-{i}",
                "title": f"Story Title {i}",
                "category": "Agents",
                "summary": f"Summary {i}",
                "why_it_matters": f"Why {i}",
                "key_takeaways": ["Takeaway"],
                "sources": [
                    {
                        "title": "Source",
                        "url": "https://source.com"
                    }
                ]
            }
            for i in range(10)  # Generates 10 items (more than the max of 5 in Edition)
        ]
    }
    
    discovery = DiscoveryEdition.model_validate(valid_discovery)
    assert len(discovery.items) == 10
    assert discovery.edition_date == "2026-08-04"

def test_ranked_news_item_validation():
    """Test that NewsItem correctly accepts and validates relevance_score, evidence_score and selection_reason."""
    item_data = {
        "id": "ranked-story",
        "title": "Ranked Story Title",
        "category": "LLMs",
        "summary": "This is a summary of the ranked story.",
        "why_it_matters": "Why it is relevant",
        "key_takeaways": ["Point"],
        "sources": [{"title": "Source", "url": "https://source.com"}],
        "relevance_score": 5,
        "evidence_score": 4,
        "selection_reason": "Chosen due to high source alignment and primary evidence"
    }
    
    item = NewsItem.model_validate(item_data)
    assert item.relevance_score == 5
    assert item.evidence_score == 4
    assert item.selection_reason == "Chosen due to high source alignment and primary evidence"
    
    # Test out-of-bounds relevance score
    bad_item_data = item_data.copy()
    bad_item_data["relevance_score"] = 10  # Must be <= 5
    
    with pytest.raises(ValidationError):
        NewsItem.model_validate(bad_item_data)

