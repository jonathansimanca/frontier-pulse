import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.script_generator import generate_podcast_script


@patch("src.script_generator.get_genai_client")
@patch("src.script_generator.load_news_data")
def test_generate_podcast_script_decoupled_english_failure(mock_load, mock_get_client, tmp_path):
    """Verify that English transcript generation failure (FP-013) does not raise an exception
    and successfully returns valid paths for both Spanish and English fallback scripts.
    """
    # 1. Setup mocked news data
    mock_news = {
        "title": "Frontier Pulse Test Edition",
        "edition_date": "2026-08-03",
        "is_slow_week": False,
        "items": [
            {
                "title": "Astra 2.0 release",
                "category": "Models",
                "summary": "Google launches Project Astra 2.0.",
                "key_takeaways": ["2x faster than previous", "High spatial context"]
            }
        ]
    }
    mock_load.return_value = mock_news

    # 2. Setup mock Gemini Client where Spanish succeeds but English fails
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # First generate call (Spanish) succeeds
    mock_response_es = MagicMock()
    mock_response_es.text = "Este es un guion de prueba en español para la edición 2026-08-03."
    
    # Second generate call (English translation) raises Exception
    mock_client.models.generate_content.side_effect = [
        mock_response_es,
        Exception("API quota limit reached or overloaded translation")
    ]

    # Patch OUTPUT_DIR and get_edition_dir for test isolation
    with patch("src.script_generator.get_edition_dir", return_value=tmp_path), \
         patch("src.script_generator.OUTPUT_DIR", tmp_path), \
         patch("src.script_generator.INPUT_DIR", tmp_path):
        
        # 3. Call generate_podcast_script
        es_path, en_path = generate_podcast_script()

        # 4. Assertions
        assert es_path == tmp_path / "podcast_script_es.txt"
        assert en_path == tmp_path / "podcast_script_en.txt"

        # Check content of Spanish script
        assert es_path.exists()
        with open(es_path, "r", encoding="utf-8") as f:
            es_content = f.read()
        assert "Este es un guion de prueba" in es_content

        # Check content of English script (should have fallback error message)
        assert en_path.exists()
        with open(en_path, "r", encoding="utf-8") as f:
            en_content = f.read()
        assert "English transcript generation failed or was skipped" in en_content
        assert "overloaded translation" in en_content
