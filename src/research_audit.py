"""Research audit trail for Frontier Pulse editions.

Writes ``output/editions/<date>/research_audit.json`` so a missed story can be diagnosed
as a discovery, filtering, or ranking problem instead of relying on aggregate logs.

The recorder saves atomically after every meaningful event (each track, pool, deduplication,
selection, and failure), so a crashed run still leaves a partial audit. Audit persistence is
best-effort: a failure to write the audit never interrupts the research pipeline.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from urllib.parse import urlparse

from src.editorial_priority import authoritative_source_urls, is_same_story
from src.schemas import (
    CandidateAudit,
    ClaimCheckAudit,
    DeduplicationAudit,
    GroundingSourceAudit,
    LinkCheckAudit,
    ResearchAttemptAudit,
    ResearchAudit,
    SelectionAudit,
    TrackAudit,
)

AUDIT_FILENAME = "research_audit.json"

NON_REJECTION_OUTCOMES = {"pending", "selected", "priority_included"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bare_domain(value: str) -> str:
    value = (value or "").strip().lower()
    return value[4:] if value.startswith("www.") else value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_urls_of(item: Any) -> list[str]:
    """Return source URLs of a raw candidate dict, tolerating malformed structures."""
    if not isinstance(item, dict):
        return []
    sources = item.get("sources")
    if not isinstance(sources, list):
        return []
    return [str(src.get("url")) for src in sources if isinstance(src, dict) and src.get("url")]


def extract_grounding_metadata(response: Any) -> tuple[list[str], list[GroundingSourceAudit]]:
    """Extract executed search queries and grounding web sources from a GenAI response.

    Works defensively with SDK objects or test doubles; returns empty lists when absent.
    """
    queries: list[str] = []
    sources: list[GroundingSourceAudit] = []
    for candidate in getattr(response, "candidates", None) or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata is None:
            continue
        for query in getattr(metadata, "web_search_queries", None) or []:
            if query and str(query) not in queries:
                queries.append(str(query))
        for chunk in getattr(metadata, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if web is None:
                continue
            uri = getattr(web, "uri", None)
            title = getattr(web, "title", None)
            if uri or title:
                sources.append(GroundingSourceAudit(title=title, uri=uri))
    return queries, sources


class ResearchAuditRecorder:
    """Collects and persists the research audit for one edition."""

    def __init__(
        self,
        edition_date: str,
        start_date: str | None,
        end_date: str | None,
        output_path: Path,
        research_model: str,
        fallback_model: str,
        max_pool_size: int,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.output_path = Path(output_path)
        self._clock = clock
        now = clock()
        self.audit = ResearchAudit(
            edition_date=edition_date,
            start_date=start_date,
            end_date=end_date,
            started_at=now,
            updated_at=now,
            research_model=research_model,
            fallback_model=fallback_model,
            max_pool_size=max_pool_size,
        )
        self.save()

    # --- persistence ------------------------------------------------------------------

    def save(self) -> bool:
        """Atomically write the audit JSON. Returns False (and logs) on failure."""
        try:
            for track in self.audit.tracks:
                track.rejections = [c for c in track.candidates if c.outcome not in NON_REJECTION_OUTCOMES]
            self.audit.updated_at = self._clock()
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.output_path.with_name(self.output_path.name + ".tmp")
            payload = json.loads(self.audit.model_dump_json())
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.output_path)
            return True
        except Exception as exc:  # Observability must never break the pipeline.
            print(f"[!] Warning: Failed to save research audit to {self.output_path}: {exc}")
            return False

    # --- discovery tracks -------------------------------------------------------------

    def _track(self, track_key: str) -> TrackAudit:
        for track in self.audit.tracks:
            if track.track == track_key:
                return track
        raise KeyError(f"Unknown audit track '{track_key}'")

    def start_track(self, track_key: str, queries: list[str], prompt: str) -> None:
        self.audit.tracks.append(
            TrackAudit(
                track=track_key,
                queries=list(queries),
                prompt=prompt,
                prompt_sha256=sha256_text(prompt),
                started_at=self._clock(),
            )
        )
        self.save()

    def record_track_attempt(
        self,
        track_key: str,
        attempt: int,
        model: str,
        temperature: float | None,
        started_at: datetime,
        duration_ms: int,
        status: str,
        error: str | None = None,
        web_search_queries: Iterable[str] = (),
        grounding_sources: Iterable[GroundingSourceAudit] = (),
        raw_response: str | None = None,
        parse_diagnostics: dict | None = None,
    ) -> None:
        diagnostics = parse_diagnostics or {}
        queries = list(web_search_queries)
        sources = list(grounding_sources)
        self._track(track_key).attempts.append(
            ResearchAttemptAudit(
                attempt=attempt,
                model=model,
                temperature=temperature,
                status=status,
                started_at=started_at,
                duration_ms=max(0, int(duration_ms)),
                error=error,
                grounded=bool(queries or sources) if status == "success" else None,
                web_search_queries=queries,
                grounding_sources=sources,
                parse_strategy=diagnostics.get("strategy"),
                parse_repairs=diagnostics.get("repairs"),
                raw_item_count=diagnostics.get("raw_item_count"),
                parsed_item_count=diagnostics.get("parsed_item_count"),
                raw_response=raw_response,
            )
        )
        self.save()

    def record_track_candidates(self, track_key: str, raw_items: list[Any]) -> None:
        """Snapshot every candidate returned by a successful attempt (before any filtering)."""
        track = self._track(track_key)
        track.candidates = [
            CandidateAudit(
                id=item.get("id") if isinstance(item, dict) else None,
                title=item.get("title") if isinstance(item, dict) else None,
                source_urls=source_urls_of(item),
            )
            for item in raw_items
        ]

    def finish_track(self, track_key: str, status: str) -> None:
        track = self._track(track_key)
        track.status = status
        track.finished_at = self._clock()
        self.save()

    # --- candidate outcomes -----------------------------------------------------------

    def _find_candidate(self, track_key: str | None, candidate_id: Any, title: Any, pending_only: bool = True) -> CandidateAudit | None:
        tracks = [self._track(track_key)] if track_key else self.audit.tracks
        for track in tracks:
            for candidate in track.candidates:
                if pending_only and candidate.outcome != "pending":
                    continue
                if candidate.id == candidate_id and candidate.title == title:
                    return candidate
        return None

    def apply_candidate_event(self, track_key: str | None, event: dict) -> None:
        """Apply an outcome event ``{id, title, stage, reason}`` to the matching candidate."""
        candidate = self._find_candidate(track_key, event.get("id"), event.get("title"))
        if candidate is None:
            return
        candidate.outcome = str(event.get("stage"))
        candidate.reason = event.get("reason")

    def apply_candidate_events(self, track_key: str | None, events: Iterable[dict]) -> None:
        for event in events:
            self.apply_candidate_event(event.get("track", track_key), event)
        self.save()

    # --- pool, deduplication, selection -----------------------------------------------

    def record_pool(self, accepted_count: int, rejections: list[dict]) -> None:
        self.audit.pool_accepted_count = accepted_count
        self.apply_candidate_events(None, rejections)

    def record_deduplication(
        self,
        history_editions_loaded: int,
        input_count: int,
        rejections: list[dict],
        candidate_tracks: dict[tuple[Any, Any], str],
        reverted_to_raw: bool,
    ) -> None:
        self.audit.deduplication = DeduplicationAudit(
            history_editions_loaded=history_editions_loaded,
            input_count=input_count,
            removed_count=len(rejections),
            reverted_to_raw=reverted_to_raw,
        )
        if not reverted_to_raw:
            events = [dict(r, track=candidate_tracks.get((r.get("id"), r.get("title")))) for r in rejections]
            self.apply_candidate_events(None, events)
        else:
            self.save()

    def start_selection(self, candidate_count: int, prompt: str, priority_signals: list[dict]) -> None:
        self.audit.selection = SelectionAudit(
            candidate_count=candidate_count,
            prompt_sha256=sha256_text(prompt),
            prompt_chars=len(prompt),
            flagged_priority_candidates=[s for s in priority_signals if s.get("flagged")],
        )
        self.save()

    def record_selection_attempt(
        self,
        attempt: int,
        model: str,
        temperature: float | None,
        started_at: datetime,
        duration_ms: int,
        status: str,
        error: str | None = None,
    ) -> None:
        if self.audit.selection is None:
            raise RuntimeError("start_selection must be called before recording selection attempts")
        self.audit.selection.attempts.append(
            ResearchAttemptAudit(
                attempt=attempt,
                model=model,
                temperature=temperature,
                status=status,
                started_at=started_at,
                duration_ms=max(0, int(duration_ms)),
                error=error,
            )
        )
        self.save()

    def annotate_priority_corroboration(
        self,
        priority_record: dict,
        candidates: list[dict],
        candidate_tracks: dict[tuple[Any, Any], str],
    ) -> None:
        """Annotate priority guard decisions with grounding corroboration (record-only).

        For each flagged decision, checks whether any authoritative source domain written by the
        model also appears among the web sources the discovery attempt was grounded on. The result
        is informational: it does not change the guard's decision.

        Adds ``grounding_corroborated`` (True/False, or None when the attempt had no grounding
        metadata) and ``grounding_note`` to each decision.
        """
        by_key = {(c.get("id"), c.get("title")): c for c in candidates}
        for decision in priority_record.get("decisions", []):
            key = (decision.get("candidate_id"), decision.get("title"))
            candidate = by_key.get(key)
            track_key = candidate_tracks.get(key)
            if candidate is None or track_key is None:
                decision["grounding_corroborated"] = None
                decision["grounding_note"] = "Candidate track could not be resolved."
                continue

            successful = [a for a in self._track(track_key).attempts if a.status == "success"]
            attempt = successful[-1] if successful else None
            if attempt is None or not attempt.grounded:
                decision["grounding_corroborated"] = None
                decision["grounding_note"] = "Discovery attempt returned no grounding metadata; sources are model-written."
                continue

            grounding_domains = set()
            for source in attempt.grounding_sources:
                if source.title:
                    grounding_domains.add(_bare_domain(source.title))
                if source.uri:
                    grounding_domains.add(_bare_domain(urlparse(source.uri).netloc))
            grounding_domains.discard("")

            trusted_domains = {_bare_domain(urlparse(url).netloc) for url in authoritative_source_urls(candidate)}
            matches = sorted(
                d for d in trusted_domains
                if any(d == g or d.endswith("." + g) or g.endswith("." + d) for g in grounding_domains)
            )
            decision["grounding_corroborated"] = bool(matches)
            decision["grounding_note"] = (
                f"Authoritative domain(s) found in grounding sources: {', '.join(matches)}."
                if matches
                else "No authoritative source domain appears in the grounding sources."
            )

    def record_selection_result(
        self,
        model_selected_items: list[dict],
        final_items: list[dict],
        priority_record: dict,
        fallback_used: bool,
        candidate_tracks: dict[tuple[Any, Any], str],
        candidates: list[dict],
        link_dropped_ids: Iterable[str] = (),
    ) -> None:
        """Record final selection and resolve outcomes for every candidate that reached selection."""
        if self.audit.selection is None:
            raise RuntimeError("start_selection must be called before recording the selection result")
        selection = self.audit.selection
        selection.fallback_used = fallback_used
        selection.selected_ids = [item.get("id") for item in final_items]
        selection.priority_guard = priority_record

        included_ids = set(priority_record.get("included_ids", []))
        dropped_ids = set(link_dropped_ids)
        stage_label = "automated fallback selection" if fallback_used else "editorial model selection"

        for candidate in candidates:
            track_key = candidate_tracks.get((candidate.get("id"), candidate.get("title")))
            audit_candidate = self._find_candidate(track_key, candidate.get("id"), candidate.get("title"))
            if audit_candidate is None:
                continue
            if candidate.get("id") in dropped_ids:
                audit_candidate.outcome = "broken_sources"
                audit_candidate.reason = f"Chosen by {stage_label}, then dropped because none of its source links worked."
            elif candidate.get("id") in included_ids:
                audit_candidate.outcome = "priority_included"
                audit_candidate.reason = "Added by the deterministic multi-lab safety/governance priority guard."
            elif any(is_same_story(candidate, item) for item in model_selected_items):
                audit_candidate.outcome = "selected"
                audit_candidate.reason = f"Chosen by {stage_label}."
            else:
                audit_candidate.outcome = "not_selected"
                audit_candidate.reason = f"Not chosen by {stage_label}."
        self.save()

    def record_link_check(self, record: dict) -> None:
        """Store the source link check record."""
        self.audit.link_check = LinkCheckAudit.model_validate(record)
        self.save()

    def record_claim_check(self, record: dict) -> None:
        """Store the edition claim-check record produced by ``src.claim_verifier``."""
        self.audit.claim_check = ClaimCheckAudit.model_validate(record)
        self.save()

    # --- run status -------------------------------------------------------------------

    def mark_completed(self) -> None:
        self.audit.status = "completed"
        self.save()

    def mark_failed(self, error: BaseException) -> None:
        self.audit.status = "failed"
        self.audit.error = f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}"[:500]
        for track in self.audit.tracks:
            if track.status == "running":
                track.status = "failed"
                track.finished_at = self._clock()
        self.save()
