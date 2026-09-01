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
    metadata: str = Field(description="Metadata line, e.g., 'Episodio 4 · 4 min'")
    cta: str = Field(default="▶ Escuchar ahora", description="Call to action line")


class InsightCardText(BaseModel):
    label: str = Field(default="ESTA SEMANA EN IA", description="Top topic label")
    title: str = Field(description="Plain-language headline for the story (max 8 words)")
    key_fact: str = Field(description="One verifiable sentence describing what happened (max 20 words)")
    why_it_matters: str = Field(description="Short practical implication starting with POR QUÉ IMPORTA: (max 16 words)")
    footer: str = Field(description="Footer line, e.g., 'FRONTIER PULSE · EPISODIO 4'")


class EditionContextCardText(BaseModel):
    label: str = Field(default="CONTEXTO DE LA EDICIÓN", description="Top label")
    title: str = Field(description="Context headline (max 8 words)")
    context_text: str = Field(description="Context or listening guidance (max 25 words)")
    cta: str = Field(default="▶ Escucha el episodio completo", description="Call to action line")
    footer: str = Field(description="Footer line, e.g., 'FRONTIER PULSE · EPISODIO 4'")


class RoundupCardText(BaseModel):
    label: str = Field(default="RADAR DE CIERRE", description="Top radar label")
    headline: str = Field(default="Más señales que debes tener en el radar", description="Fixed closing radar headline")
    remaining_titles: List[str] = Field(default_factory=list, max_length=3, description="Up to 3 remaining story titles (<= 7 words each)")
    cta: str = Field(default="Escucha el episodio completo", description="Closing call to action")
    footer: str = Field(description="Footer line, e.g., 'FRONTIER PULSE · EPISODIO 4'")


class VisualAssetItem(BaseModel):
    file: str = Field(description="Filename of the generated PNG asset (e.g. episode-4-01-cover.png)")
    type: str = Field(description="Type of asset: 'cover', 'news_insight', 'edition_context', or 'news_roundup'")
    display_order: int = Field(description="1-based suggested display order (1 to 4)")
    suggested_screen_time_seconds: int = Field(default=3, description="Recommended display duration in seconds")
    text: Union[CoverCardText, InsightCardText, EditionContextCardText, RoundupCardText, dict] = Field(description="Structured text layout data")
    source_reference: Optional[str] = Field(None, description="URL or source reference for news insight cards")


class VisualAssetManifest(BaseModel):
    episode_number: int = Field(description="Sequential episode number")
    edition_date: Optional[str] = Field(None, description="Target edition date in YYYY-MM-DD format")
    assets: List[VisualAssetItem] = Field(min_length=4, max_length=4, description="List of exactly 4 visual assets")


