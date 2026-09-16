"""Shared test doubles for exercising the research pipeline without network access."""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

import src.ia_news_researcher as researcher
import src.quality_gate as quality_gate

TRACK_NAME_PATTERN = re.compile(r"research track: '([A-Z0-9_]+)'")


def make_story(
    item_id: str,
    title: str,
    urls: tuple[str, ...] = ("https://techcrunch.com/story",),
    summary: str = "A factual summary of the development.",
    why: str = "It matters for frontier AI.",
) -> dict:
    """Build a raw discovery candidate dict as Gemini would return it."""
    return {
        "id": item_id,
        "title": title,
        "category": "Test",
        "summary": summary,
        "why_it_matters": why,
        "key_takeaways": ["Takeaway"],
        "sources": [
            {"title": f"Source {i}", "url": url, "publisher": "Publisher", "published_date": "2026-09-10"}
            for i, url in enumerate(urls)
        ],
    }


def discovery_response(items: list[dict], queries: tuple[str, ...] = (), grounding_uris: tuple[str, ...] = ()) -> SimpleNamespace:
    """Build a fake grounded discovery response with optional grounding metadata."""
    metadata = SimpleNamespace(
        web_search_queries=list(queries),
        grounding_chunks=[SimpleNamespace(web=SimpleNamespace(uri=uri, title=uri.split("/")[2])) for uri in grounding_uris],
    )
    return SimpleNamespace(
        text="```json\n" + json.dumps({"items": items}) + "\n```",
        candidates=[SimpleNamespace(grounding_metadata=metadata)],
    )


def selection_response(candidates: list[dict], chosen_ids: list[str], edition_date: str = "2026-09-14") -> SimpleNamespace:
    """Build a fake structured selection response choosing ``chosen_ids`` from ``candidates``."""
    by_id = {c["id"]: c for c in candidates}
    items = [
        dict(by_id[item_id], relevance_score=5, evidence_score=5, selection_reason="Chosen by fake editor.")
        for item_id in chosen_ids
    ]
    edition = {
        "edition_date": edition_date,
        "title": f"Frontier Pulse - Edition {edition_date}",
        "is_slow_week": False,
        "items": items,
    }
    return SimpleNamespace(text=json.dumps(edition), candidates=[])


def candidates_from_selection_prompt(prompt: str) -> list[dict]:
    """Extract the candidate pool JSON embedded in the selection prompt."""
    block = prompt.split("CANDIDATE STORIES POOL:\n", 1)[1].split("\n---", 1)[0]
    return json.loads(block)


CLAIM_CHECK_MARKER = "FACT-CHECK EDITOR"


def no_corrections_claim_check(model, prompt):
    """Default claim-check double: verifies nothing and changes nothing."""
    return SimpleNamespace(text='{"items": []}', candidates=[])


class FakeModels:
    def __init__(self, discovery_handler: Callable, selection_handler: Callable, claim_check_handler: Callable | None = None) -> None:
        self.discovery_handler = discovery_handler
        self.selection_handler = selection_handler
        self.claim_check_handler = claim_check_handler or no_corrections_claim_check
        self.discovery_calls: list[tuple[str, str]] = []
        self.selection_prompts: list[str] = []
        self.claim_check_prompts: list[str] = []

    def generate_content(self, model, contents, config):
        if getattr(config, "response_schema", None) is not None:
            self.selection_prompts.append(contents)
            return self.selection_handler(model=model, prompt=contents, attempt=len(self.selection_prompts))
        if CLAIM_CHECK_MARKER in contents:
            self.claim_check_prompts.append(contents)
            return self.claim_check_handler(model=model, prompt=contents)
        track = TRACK_NAME_PATTERN.search(contents).group(1).lower()
        self.discovery_calls.append((track, model))
        attempt = sum(1 for t, _ in self.discovery_calls if t == track)
        return self.discovery_handler(track=track, model=model, attempt=attempt, prompt=contents)


class FakeGenAIClient:
    def __init__(self, discovery_handler: Callable, selection_handler: Callable, claim_check_handler: Callable | None = None) -> None:
        self.models = FakeModels(discovery_handler, selection_handler, claim_check_handler)


def link_result(url: str, status: str = "reachable", http_status: int | None = 200, error_kind: str | None = None) -> dict:
    return {"url": url, "status": status, "http_status": http_status, "error": None if error_kind is None else error_kind, "error_kind": error_kind}


def all_links_reachable(urls, **_kwargs) -> dict:
    return {str(u): link_result(str(u)) for u in urls}


@pytest.fixture
def research_env(monkeypatch, tmp_path):
    """Redirect research outputs to a temp directory, disable sleeps, and allow a fake client."""
    output_dir = tmp_path / "output"
    history_dir = output_dir / "history"
    input_dir = tmp_path / "input"
    for directory in (output_dir, history_dir, input_dir):
        directory.mkdir(parents=True, exist_ok=True)

    def edition_dir(edition_date: str) -> Path:
        path = output_dir / "editions" / edition_date
        path.mkdir(parents=True, exist_ok=True)
        return path

    monkeypatch.setattr(researcher, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(researcher, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(researcher, "INPUT_DIR", input_dir)
    monkeypatch.setattr(researcher, "get_edition_dir", edition_dir)
    monkeypatch.setattr(quality_gate, "get_edition_dir", edition_dir)
    monkeypatch.setattr(researcher.time, "sleep", lambda _seconds: None)
    # Never touch the network in tests: every source link is reachable unless a test overrides it.
    monkeypatch.setattr(researcher, "check_urls", all_links_reachable)

    def install_client(client: FakeGenAIClient) -> FakeGenAIClient:
        monkeypatch.setattr(researcher, "get_genai_client", lambda: client)
        return client

    def write_history(edition: dict) -> None:
        (history_dir / f"history_{edition['edition_date']}.json").write_text(json.dumps(edition), encoding="utf-8")

    return SimpleNamespace(
        output_dir=output_dir,
        history_dir=history_dir,
        input_dir=input_dir,
        edition_dir=edition_dir,
        install_client=install_client,
        write_history=write_history,
    )
