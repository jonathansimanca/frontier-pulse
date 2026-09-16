from datetime import datetime, timezone
from typing import List, Optional, Union
from pydantic import BaseModel, Field, HttpUrl

class SourceReference(BaseModel):
    title: str = Field(
        description="Title or name of the source webpage, article, or official announcement"
    )
    url: HttpUrl = Field(
        description="Canonical URL of the source"
    )
    publisher: Optional[str] = Field(
        None,
        description="Publisher, organization, or platform name (e.g., 'OpenAI Blog', 'Anthropic Research')"
    )
    published_date: Optional[str] = Field(
        None,
        description="Estimated publication date of the source in YYYY-MM-DD or ISO 8601 format"
    )

class NewsItem(BaseModel):
    id: str = Field(
        description="A unique, stable and lowercase hyphenated identifier for this story (e.g., 'gemini-1.5-pro-updates')"
    )
    title: str = Field(
        description="Clear, descriptive and professional title of the news development"
    )
    category: str = Field(
        description="Category name (e.g., 'LLMs', 'Open Source', 'Autonomous Agents', 'AI Governance')"
    )
    summary: str = Field(
        description="Detailed, factual 2-3 sentence summary of the breakthrough, technical details and its immediate implications."
    )
    why_it_matters: str = Field(
        description="Clear explanation of why this development is highly relevant to frontier AI technology watch."
    )
    key_takeaways: List[str] = Field(
        min_length=1,
        max_length=5,
        description="A list of 1 to 5 highly specific, evidence-backed takeaways or technical bullet points"
    )
    sources: List[SourceReference] = Field(
        min_length=1,
        description="A list of at least one valid and verified source with a canonical URL"
    )
    relevance_score: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Relevance score to frontier AI priority areas (1 to 5)"
    )
    evidence_score: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Evidence and source grounding strength score (1 to 5)"
    )
    selection_reason: Optional[str] = Field(
        None,
        description="Brief explanation of why this item was selected or ranked"
    )

class Edition(BaseModel):
    edition_date: str = Field(
        description="The target edition date in YYYY-MM-DD format"
    )
    start_date: Optional[str] = Field(
        None,
        description="The start timestamp of the research window (e.g. YYYY-MM-DDTHH:MM:SS-05:00)"
    )
    end_date: Optional[str] = Field(
        None,
        description="The end timestamp of the research window (e.g. YYYY-MM-DDTHH:MM:SS-05:00)"
    )
    title: str = Field(
        description="The title of this edition, e.g., 'Frontier Pulse - Edition YYYY-MM-DD: Key Highlights'"
    )
    is_slow_week: bool = Field(
        description="Set to true if there are fewer than 2 major new announcements this week, otherwise false"
    )
    generation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the edition was generated"
    )
    items: List[NewsItem] = Field(
        min_length=1,
        max_length=5,
        description="Selected top-tier news items for this edition (typically 3 to 4 items)"
    )

class DiscoveryEdition(BaseModel):
    edition_date: str = Field(
        description="The target edition date in YYYY-MM-DD format"
    )
    start_date: Optional[str] = Field(
        None,
        description="The start timestamp of the research window (e.g. YYYY-MM-DDTHH:MM:SS-05:00)"
    )
    end_date: Optional[str] = Field(
        None,
        description="The end timestamp of the research window (e.g. YYYY-MM-DDTHH:MM:SS-05:00)"
    )
    # max_length must stay equal to MAX_DISCOVERY_POOL_SIZE in src/config.py.
    items: List[NewsItem] = Field(
        min_length=1,
        max_length=35,
        description="The pool of candidates discovered across all research tracks"
    )

class DeliveryState(BaseModel):
    text_delivered: bool = False
    audio_delivered: bool = False
    image_delivered: bool = False
    telegram_message_id: Optional[int] = None
    telegram_audio_message_id: Optional[int] = None
    telegram_image_message_id: Optional[int] = None

class EditionManifest(BaseModel):
    edition_id: str = Field(description="Format: YYYY-MM-DD")
    edition_date: str = Field(description="Format: YYYY-MM-DD")
    status: str = Field(default="created", description="Enum: created, researched, scripted, audio_ready, delivered, completed, failed")
    last_successful_stage: Optional[str] = None
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    artifacts: dict = Field(default_factory=dict, description="File paths for generated artifacts")
    delivery_state: DeliveryState = Field(default_factory=DeliveryState)


class GroundingSourceAudit(BaseModel):
    title: Optional[str] = Field(None, description="Title reported by Search Grounding (often the publisher domain)")
    uri: Optional[str] = Field(None, description="Grounding chunk URI (may be a vertexaisearch redirect URL)")


class ResearchAttemptAudit(BaseModel):
    attempt: int = Field(description="1-based attempt number within the track or stage")
    model: str = Field(description="Gemini model used for this attempt")
    temperature: Optional[float] = None
    status: str = Field(description="Enum: success, error")
    started_at: datetime
    duration_ms: int = Field(ge=0)
    error: Optional[str] = Field(None, description="Single-line error summary when status is error")
    grounded: Optional[bool] = Field(
        None,
        description="For successful discovery attempts: True when the response carried grounding metadata (searches or web sources)",
    )
    web_search_queries: List[str] = Field(default_factory=list, description="Searches actually executed by the model (grounding metadata)")
    grounding_sources: List[GroundingSourceAudit] = Field(default_factory=list, description="Web sources used by grounding")


class CandidateAudit(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    source_urls: List[str] = Field(default_factory=list, description="Source URLs exactly as returned by discovery")
    outcome: str = Field(
        default="pending",
        description=(
            "Enum: pending, selected, priority_included, not_selected, broken_sources, missing_sources, "
            "blocked_domain_sources, schema_validation, pool_duplicate_title, pool_size_cap, "
            "historical_url_match, historical_title_similarity"
        ),
    )
    reason: Optional[str] = Field(None, description="Human-readable explanation for the outcome")


class TrackAudit(BaseModel):
    track: str
    status: str = Field(default="running", description="Enum: running, success, failed")
    queries: List[str]
    prompt: str
    prompt_sha256: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    attempts: List[ResearchAttemptAudit] = Field(default_factory=list)
    candidates: List[CandidateAudit] = Field(default_factory=list, description="Every candidate returned by the successful attempt")
    rejections: List[CandidateAudit] = Field(default_factory=list, description="Candidates that did not reach the edition, with reasons")


class DeduplicationAudit(BaseModel):
    history_editions_loaded: int = 0
    input_count: int = 0
    removed_count: int = 0
    reverted_to_raw: bool = Field(False, description="True when every candidate was removed and the raw pool was used instead")


class SelectionAudit(BaseModel):
    candidate_count: int = 0
    prompt_sha256: Optional[str] = None
    prompt_chars: int = 0
    flagged_priority_candidates: List[dict] = Field(default_factory=list)
    attempts: List[ResearchAttemptAudit] = Field(default_factory=list)
    fallback_used: bool = False
    selected_ids: List[Optional[str]] = Field(default_factory=list)
    priority_guard: Optional[dict] = None


class LinkCheckResultAudit(BaseModel):
    url: str
    status: str = Field(description="Enum: reachable, blocked, broken, unverified")
    http_status: Optional[int] = None
    error: Optional[str] = None
    error_kind: Optional[str] = Field(None, description="Enum: dns, connection, timeout, invalid_url, request")


class LinkCheckAudit(BaseModel):
    status: str = Field(description="Enum: skipped, success, network_unavailable")
    duration_ms: int = Field(0, ge=0)
    results: List[LinkCheckResultAudit] = Field(default_factory=list)
    removed_urls: dict = Field(default_factory=dict, description="Story or candidate id -> broken source URLs removed")
    dropped_story_ids: List[str] = Field(default_factory=list, description="Selected stories dropped because no working link remained")
    excluded_candidate_ids: List[str] = Field(default_factory=list, description="Flagged candidates excluded from the priority guard for lack of working links")
    slow_week_adjusted: bool = False
    note: Optional[str] = None


class ClaimCheckItemAudit(BaseModel):
    id: Optional[str] = None
    verdict: str = Field(description="Enum: supported, corrected, not_checked, invalid_correction")
    changed_fields: List[str] = Field(default_factory=list)
    removed_claims: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class ClaimCheckAudit(BaseModel):
    status: str = Field(description="Enum: skipped, success, error")
    model: str
    started_at: datetime
    duration_ms: int = Field(ge=0)
    grounded: Optional[bool] = None
    web_search_queries: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    ignored_ids: List[str] = Field(default_factory=list)
    items: List[ClaimCheckItemAudit] = Field(default_factory=list)


class ResearchAudit(BaseModel):
    """Per-edition research audit trail used to diagnose discovery, filtering, or ranking misses."""

    edition_date: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = Field(default="running", description="Enum: running, completed, failed")
    started_at: datetime
    updated_at: datetime
    research_model: str
    fallback_model: str
    max_pool_size: int
    tracks: List[TrackAudit] = Field(default_factory=list)
    pool_accepted_count: Optional[int] = None
    deduplication: Optional[DeduplicationAudit] = None
    selection: Optional[SelectionAudit] = None
    link_check: Optional[LinkCheckAudit] = None
    claim_check: Optional[ClaimCheckAudit] = None
    error: Optional[str] = None


class QualityCheckResult(BaseModel):
    check_name: str
    passed: bool
    message: str


class EditorialQualityReport(BaseModel):
    edition_date: str
    passed: bool
    checks: List[QualityCheckResult]
    slow_week_adjustment: bool = False
    reasons_for_failure: List[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CoverCardText(BaseModel):
    series: str = Field(default="FRONTIER PULSE", description="Top series label")
    format: str = Field(default="PODCAST SEMANAL DE IA", description="Supporting format label")
    headline: str = Field(description="Benefit-led main headline (max 8 words)")
    metadata: str = Field(description="Metadata line with release date and duration, e.g., '21 sep 2026 · 4 min'")
    cta: str = Field(default="Escuchar ahora", description="Call to action line")


class InsightCardText(BaseModel):
    label: str = Field(default="ESTA SEMANA EN IA", description="Top topic label")
    title: str = Field(description="Plain-language headline for the story (max 8 words)")
    key_fact: str = Field(description="One verifiable sentence describing what happened (max 20 words)")
    why_it_matters: str = Field(description="Short practical implication starting with POR QUÉ IMPORTA: (max 16 words)")
    footer: str = Field(description="Footer line with release date, e.g., 'FRONTIER PULSE · 21 SEP 2026'")


class EditionContextCardText(BaseModel):
    label: str = Field(default="CONTEXTO DE LA EDICIÓN", description="Top label")
    title: str = Field(description="Context headline (max 8 words)")
    context_text: str = Field(description="Context or listening guidance (max 25 words)")
    cta: str = Field(default="Escucha el episodio completo", description="Call to action line")
    footer: str = Field(description="Footer line with release date, e.g., 'FRONTIER PULSE · 21 SEP 2026'")


class RoundupCardText(BaseModel):
    label: str = Field(default="", description="Deprecated legacy field; no longer rendered")
    headline: str = Field(default="También esta semana", description="Concise heading for the remaining-news list")
    remaining_titles: List[str] = Field(default_factory=list, max_length=3, description="Up to 3 remaining story titles (<= 7 words each)")
    cta: str = Field(default="Escucha el episodio completo", description="Closing call to action")
    footer: str = Field(description="Footer line with release date, e.g., 'FRONTIER PULSE · 21 SEP 2026'")


class VisualAssetItem(BaseModel):
    file: str = Field(description="Filename of the generated PNG asset (e.g. edition-2026-09-21-01-cover.png)")
    type: str = Field(description="Type of asset: 'cover', 'news_insight', 'edition_context', or 'news_roundup'")
    display_order: int = Field(description="1-based suggested display order (1 to 4)")
    suggested_screen_time_seconds: int = Field(default=3, description="Recommended display duration in seconds")
    text: Union[CoverCardText, InsightCardText, EditionContextCardText, RoundupCardText, dict] = Field(description="Structured text layout data")
    source_reference: Optional[str] = Field(None, description="URL or source reference for news insight cards")


class VisualAssetManifest(BaseModel):
    edition_date: Optional[str] = Field(None, description="Target edition date in YYYY-MM-DD format")
    assets: List[VisualAssetItem] = Field(min_length=4, max_length=4, description="List of exactly 4 visual assets")

