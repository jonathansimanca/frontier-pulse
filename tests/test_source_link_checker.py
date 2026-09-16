"""Tests for source link verification (no real network access)."""

import json
import socket
from types import SimpleNamespace

import pytest
import requests
from urllib3.exceptions import MaxRetryError

import src.ia_news_researcher as researcher
from conftest import FakeGenAIClient, candidates_from_selection_prompt, discovery_response, link_result, make_story, selection_response
from src.quality_gate import validate_edition_quality
from src.research_audit import AUDIT_FILENAME
from src.source_link_checker import (
    check_url,
    check_urls,
    classify_status_code,
    network_unavailable,
    remove_broken_sources,
)

EDITION_DATE = "2026-09-14"


class FakeSession:
    """Scripted HEAD/GET responses per URL; values are status codes or exceptions."""

    def __init__(self, head, get=None):
        self.head_script = head
        self.get_script = get or {}
        self.calls = []
        self.closed = []

    def _answer(self, method, script, url):
        self.calls.append((method, url))
        value = script[url]
        if isinstance(value, BaseException):
            raise value
        response = SimpleNamespace(status_code=value, close=lambda: self.closed.append(url))
        return response

    def head(self, url, **kwargs):
        assert kwargs["allow_redirects"] is True and kwargs["timeout"] == 5.0
        return self._answer("HEAD", self.head_script, url)

    def get(self, url, **kwargs):
        assert kwargs["stream"] is True
        return self._answer("GET", self.get_script, url)


# --- Classification -------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, expected",
    [(200, "reachable"), (301, "reachable"), (404, "broken"), (410, "broken"), (401, "blocked"),
     (403, "blocked"), (429, "blocked"), (400, "unverified"), (500, "unverified"), (503, "unverified")],
)
def test_classify_status_code(code, expected):
    assert classify_status_code(code) == expected


def test_head_success_does_not_issue_get():
    session = FakeSession(head={"https://a.test/x": 200})
    result = check_url("https://a.test/x", session=session)
    assert result == {"url": "https://a.test/x", "status": "reachable", "http_status": 200, "error": None, "error_kind": None}
    assert session.calls == [("HEAD", "https://a.test/x")]


@pytest.mark.parametrize(
    "head, get, expected_status",
    [(405, 200, "reachable"), (404, 200, "reachable"), (404, 404, "broken"), (410, 410, "broken"),
     (403, 403, "blocked"), (500, 502, "unverified")],
)
def test_non_success_head_is_confirmed_with_get(head, get, expected_status):
    url = "https://a.test/page"
    session = FakeSession(head={url: head}, get={url: get})
    result = check_url(url, session=session)
    assert result["status"] == expected_status
    assert result["http_status"] == get
    assert session.calls == [("HEAD", url), ("GET", url)]
    assert session.closed == [url]


def test_timeout_is_unverified_not_broken():
    url = "https://slow.test/"
    result = check_url(url, session=FakeSession(head={url: requests.exceptions.ReadTimeout("timed out")}))
    assert (result["status"], result["error_kind"]) == ("unverified", "timeout")


def test_dns_failure_is_broken():
    url = "https://does-not-exist.test/"
    dns_error = requests.exceptions.ConnectionError(socket.gaierror(-2, "Name or service not known"))
    result = check_url(url, session=FakeSession(head={url: dns_error}))
    assert (result["status"], result["error_kind"]) == ("broken", "dns")


def test_urllib3_style_resolution_failure_is_broken():
    url = "https://made-up-publisher.test/story"
    wrapped = requests.exceptions.ConnectionError(
        MaxRetryError(pool=None, url="/story", reason=Exception("Failed to resolve 'made-up-publisher.test'"))
    )
    assert check_url(url, session=FakeSession(head={url: wrapped}))["status"] == "broken"


def test_other_connection_error_is_unverified():
    url = "https://reset.test/"
    error = requests.exceptions.ConnectionError("Connection reset by peer")
    result = check_url(url, session=FakeSession(head={url: error}))
    assert (result["status"], result["error_kind"]) == ("unverified", "connection")


def test_check_urls_deduplicates_and_keys_by_url():
    calls = []

    def checker(url, timeout):
        calls.append(url)
        return link_result(url)

    results = check_urls(["https://a.test/1", "https://a.test/1", "https://b.test/2", ""], checker=checker)

    assert sorted(calls) == ["https://a.test/1", "https://b.test/2"]
    assert set(results) == {"https://a.test/1", "https://b.test/2"}
    assert check_urls([], checker=checker) == {}


def test_network_unavailable_only_when_every_link_fails_at_network_level():
    offline = {"u1": link_result("u1", "broken", None, "dns"), "u2": link_result("u2", "unverified", None, "timeout")}
    assert network_unavailable(offline) is True
    assert network_unavailable({**offline, "u3": link_result("u3")}) is False
    assert network_unavailable({"u4": link_result("u4", "broken", 404)}) is False
    assert network_unavailable({}) is False


def test_remove_broken_sources_keeps_other_links_and_drops_empty_items():
    partial = make_story("partial", "Partial", urls=("https://ok.test/a", "https://broken.test/a"))
    empty = make_story("empty", "Empty", urls=("https://broken.test/b",))
    results = {
        "https://ok.test/a": link_result("https://ok.test/a"),
        "https://broken.test/a": link_result("https://broken.test/a", "broken", 404),
        "https://broken.test/b": link_result("https://broken.test/b", "broken", None, "dns"),
    }

    kept, removed, dropped = remove_broken_sources([partial, empty], results)

    assert [i["id"] for i in kept] == ["partial"]
    assert [s["url"] for s in kept[0]["sources"]] == ["https://ok.test/a"]
    assert removed == {"partial": ["https://broken.test/a"], "empty": ["https://broken.test/b"]}
    assert dropped == ["empty"]
    assert len(partial["sources"]) == 2, "Input must not be mutated"


# --- Pipeline integration -------------------------------------------------------------

STORY_PARTIAL = make_story("story-partial", "Chipmaker Ships New Accelerator", urls=("https://techcrunch.com/ok", "https://techcrunch.com/missing"))
STORY_BROKEN = make_story("story-broken", "Startup Claims Record Benchmark", urls=("https://made-up.test/claim",))
STORY_OK = make_story("story-ok", "Open Model Tops Leaderboard", urls=("https://huggingface.co/model",))
FLAGGED = make_story(
    "labs-pace-frontier",
    "Anthropic and OpenAI Leaders Call to Pace the Frontier",
    urls=("https://www.theguardian.com/technology/fake-path", "https://darioamodei.com/essay"),
    summary="Anthropic CEO Dario Amodei and OpenAI CEO Sam Altman issued a joint statement to slow down frontier AI development.",
)

BROKEN_URLS = {"https://techcrunch.com/missing", "https://made-up.test/claim", "https://www.theguardian.com/technology/fake-path"}


def _statuses(urls, **_kwargs):
    return {u: (link_result(u, "broken", 404) if u in BROKEN_URLS else link_result(u)) for u in urls}


def _run(research_env, monkeypatch, checker, stories, chosen_ids):
    monkeypatch.setattr(researcher, "check_urls", checker)

    def discovery(track, model, attempt, prompt):
        return discovery_response(stories if track == "frontier_labs" else [])

    def editor(model, prompt, attempt):
        return selection_response(candidates_from_selection_prompt(prompt), chosen_ids)

    research_env.install_client(FakeGenAIClient(discovery, editor))
    return researcher.research_ai_news(EDITION_DATE)


def _audit(research_env):
    return json.loads((research_env.edition_dir(EDITION_DATE) / AUDIT_FILENAME).read_text(encoding="utf-8"))


def _candidate(audit, candidate_id):
    return next(c for t in audit["tracks"] for c in t["candidates"] if c["id"] == candidate_id)


def test_pipeline_drops_broken_links_and_linkless_stories_and_marks_slow_week(research_env, monkeypatch):
    news_data = _run(research_env, monkeypatch, _statuses, [STORY_PARTIAL, STORY_BROKEN, STORY_OK, FLAGGED],
                     ["story-partial", "story-broken", "story-ok"])

    assert [i["id"] for i in news_data["items"]] == ["story-partial", "story-ok"]
    assert [s["url"] for s in news_data["items"][0]["sources"]] == ["https://techcrunch.com/ok"]
    assert news_data["is_slow_week"] is True
    assert validate_edition_quality(news_data).passed

    audit = _audit(research_env)
    link = audit["link_check"]
    assert link["status"] == "success"
    assert link["dropped_story_ids"] == ["story-broken"]
    assert link["removed_urls"]["story-partial"] == ["https://techcrunch.com/missing"]
    assert link["slow_week_adjusted"] is True
    checked = {r["url"]: r["status"] for r in link["results"]}
    assert checked["https://made-up.test/claim"] == "broken"
    assert checked["https://darioamodei.com/essay"] == "reachable"

    broken = _candidate(audit, "story-broken")
    assert broken["outcome"] == "broken_sources"
    assert "none of its source links worked" in broken["reason"]

    # The flagged story's only authoritative link (theguardian.com) is broken, so the guard does not add it.
    decisions = {d["candidate_id"]: d["action"] for d in audit["selection"]["priority_guard"]["decisions"]}
    assert decisions == {"labs-pace-frontier": "skipped_no_authoritative_source"}
    assert audit["link_check"]["removed_urls"]["labs-pace-frontier"] == ["https://www.theguardian.com/technology/fake-path"]


def test_pipeline_includes_flagged_story_only_with_its_working_links(research_env, monkeypatch):
    flagged = dict(FLAGGED, sources=FLAGGED["sources"] + [{"title": "Reuters", "url": "https://www.reuters.com/tech/pace"}])

    news_data = _run(research_env, monkeypatch, _statuses, [STORY_OK, flagged], ["story-ok"])

    added = next(i for i in news_data["items"] if i["id"] == "labs-pace-frontier")
    assert [s["url"] for s in added["sources"]] == ["https://darioamodei.com/essay", "https://www.reuters.com/tech/pace"]
    assert _audit(research_env)["selection"]["priority_guard"]["included_ids"] == ["labs-pace-frontier"]


def test_pipeline_removes_nothing_when_network_is_unavailable(research_env, monkeypatch):
    def offline(urls, **_kwargs):
        return {u: link_result(u, "broken", None, "dns") for u in urls}

    news_data = _run(research_env, monkeypatch, offline, [STORY_PARTIAL, STORY_BROKEN, STORY_OK], ["story-partial", "story-broken", "story-ok"])

    assert [i["id"] for i in news_data["items"]] == ["story-partial", "story-broken", "story-ok"]
    assert len(news_data["items"][0]["sources"]) == 2
    link = _audit(research_env)["link_check"]
    assert link["status"] == "network_unavailable"
    assert link["dropped_story_ids"] == []


def test_pipeline_fails_when_no_selected_story_has_a_working_link(research_env, monkeypatch):
    with pytest.raises(RuntimeError, match="No selected story has a working source link"):
        _run(research_env, monkeypatch, _statuses, [STORY_BROKEN, STORY_OK], ["story-broken"])

    audit = _audit(research_env)
    assert audit["status"] == "failed"
    assert audit["link_check"]["dropped_story_ids"] == ["story-broken"]


def test_link_check_can_be_disabled(research_env, monkeypatch):
    monkeypatch.setattr(researcher, "LINK_CHECK_ENABLED", False)

    def must_not_run(urls, **_kwargs):
        raise AssertionError("link check should be disabled")

    news_data = _run(research_env, monkeypatch, must_not_run, [STORY_BROKEN, STORY_OK], ["story-broken", "story-ok"])

    assert [i["id"] for i in news_data["items"]] == ["story-broken", "story-ok"]
    assert _audit(research_env)["link_check"]["status"] == "skipped"
