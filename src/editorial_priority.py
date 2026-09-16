"""Deterministic editorial priority signals for multi-lab frontier AI safety and governance stories.

Story ranking in Frontier Pulse is performed by Gemini using the editorial rubric. This
module adds a narrow, explainable safeguard for one class of high-impact developments that
the pipeline previously missed: coordinated safety or governance actions involving multiple
frontier AI labs (for example, lab leaders jointly calling for a slower pace of frontier AI
development).

The classifier intentionally favors precision over recall because a flagged candidate can be
force-included into an edition. A candidate is flagged only when BOTH conditions hold:

1. At least ``MIN_LABS_FOR_PRIORITY`` distinct frontier labs are named, and
2. At least one specific safety/governance action phrase is present (generic words such as
   "safety", "evaluation", or "regulation" alone never qualify).

Single-lab policy updates and regulator-only actions are intentionally not flagged; the
editorial rubric covers them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from src.config import AUTHORITATIVE_DOMAINS

PRIORITY_CATEGORY = "multi_lab_frontier_safety_governance"
MIN_LABS_FOR_PRIORITY = 2
MAX_PRIORITY_INCLUSIONS_PER_EDITION = 1
MAX_EDITION_ITEMS = 5

# Canonical frontier lab -> case-insensitive patterns (word-bounded).
FRONTIER_LAB_ALIASES: dict[str, list[str]] = {
    "anthropic": [r"anthropic", r"claude"],
    "openai": [r"openai", r"chatgpt"],
    "xai": [r"xai", r"x\.ai", r"grok"],
    "google_deepmind": [r"google deepmind", r"deepmind", r"google", r"gemini"],
    "meta": [r"meta ai", r"meta superintelligence", r"meta", r"llama"],
    "microsoft": [r"microsoft"],
    "mistral": [r"mistral ai", r"mistral"],
    "deepseek": [r"deepseek"],
}

# Canonical signal label -> case-insensitive patterns (word-bounded).
SAFETY_GOVERNANCE_ACTION_SIGNALS: dict[str, list[str]] = {
    "development slowdown": [
        r"slow(?:ing)? down",
        r"slowdown",
        r"slower (?:pace|development)",
        r"slow(?:er|ing)? the pace",
        r"pac(?:e|es|ed|ing) the frontier",
        # Verb forms only: the noun phrase "the pace of AI development" is common in ordinary news.
        r"pac(?:e|es|ed|ing) (?:frontier )?(?:ai )?development",
    ],
    "development pause or halt": [
        r"pause[sd]?",
        r"pausing",
        r"halt(?:s|ed|ing)?",
        r"moratorium",
    ],
    "capability limits": [
        r"capability (?:limits?|restrictions?|caps?)",
        r"limits? on (?:frontier |ai |model )?capabilit(?:y|ies)",
        r"restrict(?:ing|ions? on)? (?:frontier )?(?:ai )?capabilit(?:y|ies)",
    ],
    "joint or coordinated safety action": [
        r"joint (?:statement|commitment|letter|declaration|pledge)",
        r"open letter",
        r"coordinated (?:safety|action|commitment|pause|slowdown)",
        r"(?:safety|voluntary) commitments?",
        r"safety pledge",
    ],
    "frontier risk thresholds": [
        r"(?:risk|deployment|capability) thresholds?",
        r"catastrophic[- ]risks?",
        r"existential[- ]risks?",
    ],
    "independent safety evaluation": [
        r"independent (?:third[- ]party )?(?:safety )?(?:evaluations?|evaluators?|testing|audits?)",
        r"external (?:safety )?evaluators?",
        r"pre[- ]deployment (?:safety )?testing",
    ],
    "international safety coordination": [
        r"international (?:ai )?safety (?:agreement|accord|treaty|coordination|summit)",
        r"(?:ai|frontier) safety (?:agreement|accord|treaty)",
    ],
}


def _compile(patterns: dict[str, list[str]]) -> dict[str, re.Pattern]:
    return {
        label: re.compile(r"\b(?:" + "|".join(alternatives) + r")\b", re.IGNORECASE)
        for label, alternatives in patterns.items()
    }


_LAB_REGEXES = _compile(FRONTIER_LAB_ALIASES)
_SIGNAL_REGEXES = _compile(SAFETY_GOVERNANCE_ACTION_SIGNALS)


@dataclass(frozen=True)
class PrioritySignal:
    """Explainable result of classifying one candidate story."""

    candidate_id: str | None
    title: str | None
    flagged: bool
    category: str | None
    labs: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "flagged": self.flagged,
            "category": self.category,
            "labs": list(self.labs),
            "signals": list(self.signals),
            "reason": self.reason,
        }


def _story_text(item: dict) -> str:
    """Return the editorial text used for classification (excludes publisher names and URLs)."""
    parts = [
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        str(item.get("why_it_matters") or ""),
    ]
    parts.extend(str(t) for t in (item.get("key_takeaways") or []))
    return "\n".join(parts)


def detect_frontier_labs(text: str) -> list[str]:
    """Return the sorted canonical frontier labs named in ``text``."""
    return sorted(lab for lab, regex in _LAB_REGEXES.items() if regex.search(text))


def detect_safety_governance_signals(text: str) -> list[str]:
    """Return the sorted safety/governance action signal labels found in ``text``."""
    return sorted(label for label, regex in _SIGNAL_REGEXES.items() if regex.search(text))


def classify_priority(item: dict) -> PrioritySignal:
    """Classify whether a candidate is a multi-lab frontier AI safety/governance priority story."""
    text = _story_text(item)
    labs = detect_frontier_labs(text)
    signals = detect_safety_governance_signals(text)
    flagged = len(labs) >= MIN_LABS_FOR_PRIORITY and bool(signals)

    if flagged:
        reason = f"Names {len(labs)} frontier labs ({', '.join(labs)}) with safety/governance action signals ({', '.join(signals)})."
    elif not signals:
        reason = "No specific safety/governance action signal."
    else:
        reason = f"Safety/governance signals present but fewer than {MIN_LABS_FOR_PRIORITY} frontier labs named."

    return PrioritySignal(
        candidate_id=item.get("id"),
        title=item.get("title"),
        flagged=flagged,
        category=PRIORITY_CATEGORY if flagged else None,
        labs=labs,
        signals=signals,
        reason=reason,
    )


def classify_candidates(candidates: list[dict]) -> list[PrioritySignal]:
    """Classify every candidate, preserving order."""
    return [classify_priority(item) for item in candidates]


def _domain(url: str) -> str:
    try:
        netloc = urlparse(str(url)).netloc.lower()
    except ValueError:
        return ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def is_authoritative_domain(domain: str) -> bool:
    """Return True when ``domain`` equals or is a subdomain of an authoritative domain."""
    return any(domain == d or domain.endswith("." + d) for d in AUTHORITATIVE_DOMAINS)


def authoritative_source_urls(item: dict) -> list[str]:
    """Return source URLs of ``item`` that belong to authoritative domains."""
    return [
        str(src.get("url"))
        for src in item.get("sources", []) or []
        if src.get("url") and is_authoritative_domain(_domain(src["url"]))
    ]


GROUNDING_REDIRECT_DOMAIN = "vertexaisearch.cloud.google.com"


def _has_only_grounding_redirects(item: dict) -> bool:
    """Return True when every source is a Search Grounding redirect URL (publisher unverifiable)."""
    domains = [_domain(src.get("url", "")) for src in item.get("sources", []) or []]
    return bool(domains) and all(d == GROUNDING_REDIRECT_DOMAIN for d in domains)


def _normalize_url(url: str) -> str:
    url = str(url).strip().lower().split("?")[0].split("#")[0]
    return url.rstrip("/")


def _source_url_set(item: dict) -> set[str]:
    return {_normalize_url(s.get("url", "")) for s in item.get("sources", []) or [] if s.get("url")}


def is_same_story(candidate: dict, other: dict) -> bool:
    """Return True when two story dicts refer to the same development.

    Matches by id, normalized title, or any shared normalized source URL, because the
    selection model may rewrite ids or titles.
    """
    cand_id = candidate.get("id")
    if cand_id and other.get("id") == cand_id:
        return True
    cand_title = str(candidate.get("title") or "").strip().lower()
    if cand_title and str(other.get("title") or "").strip().lower() == cand_title:
        return True
    return bool(_source_url_set(candidate) & _source_url_set(other))


def _is_already_selected(candidate: dict, selected_items: list[dict]) -> bool:
    return any(is_same_story(candidate, selected) for selected in selected_items)


def enforce_priority_inclusion(edition: dict, candidates: list[dict]) -> tuple[dict, dict]:
    """Ensure a verified multi-lab safety/governance story is not dropped by model selection.

    Rules (approved editorial policy):
    - Only candidates flagged by :func:`classify_priority` are considered.
    - A flagged candidate already present in the edition needs no action.
    - When the edition already contains any flagged story, nothing is added: different
      discovery tracks often return the same event under different titles and URLs, and
      the guard exists to ensure coverage of the event class, not to add duplicates.
    - A flagged candidate must cite at least one source from ``AUTHORITATIVE_DOMAINS``.
    - The candidate is appended (never replacing a selected story) only while the edition
      holds fewer than ``MAX_EDITION_ITEMS`` items.
    - At most ``MAX_PRIORITY_INCLUSIONS_PER_EDITION`` candidates are added per edition.

    Args:
        edition: Finalized edition dict (``Edition``-compatible). It is not mutated.
        candidates: Candidate dicts that were eligible for selection (after deduplication).

    Returns:
        ``(edition, record)`` where ``edition`` is a new dict (possibly with an added item)
        and ``record`` is a JSON-compatible audit record describing every decision.
    """
    selected_items = list(edition.get("items", []))
    signals = classify_candidates(candidates)
    selected_priority_ids = [item.get("id") for item in selected_items if classify_priority(item).flagged]
    decisions: list[dict] = []
    eligible: list[tuple[int, dict, PrioritySignal, list[str], dict]] = []

    for index, (candidate, signal) in enumerate(zip(candidates, signals)):
        if not signal.flagged:
            continue
        decision = signal.to_dict()
        if _is_already_selected(candidate, selected_items):
            decision["action"] = "already_selected"
        elif selected_priority_ids:
            decision["action"] = "skipped_priority_story_already_selected"
            decision["selected_priority_ids"] = selected_priority_ids
        else:
            trusted_urls = authoritative_source_urls(candidate)
            if not trusted_urls:
                decision["action"] = (
                    "skipped_only_grounding_redirect_sources"
                    if _has_only_grounding_redirects(candidate)
                    else "skipped_no_authoritative_source"
                )
            else:
                decision["action"] = "pending"
                decision["authoritative_sources"] = trusted_urls
                eligible.append((index, candidate, signal, trusted_urls, decision))
        decisions.append(decision)

    # Strongest first: more labs, then more authoritative sources, then discovery order.
    eligible.sort(key=lambda entry: (-len(entry[2].labs), -len(entry[3]), entry[0]))

    added_items: list[dict] = []
    for _, candidate, signal, trusted_urls, decision in eligible:
        if len(added_items) >= MAX_PRIORITY_INCLUSIONS_PER_EDITION:
            decision["action"] = "skipped_inclusion_limit_reached"
            continue
        if len(selected_items) + len(added_items) >= MAX_EDITION_ITEMS:
            decision["action"] = "skipped_edition_full"
            continue

        forced_item = dict(candidate)
        forced_item["relevance_score"] = 5
        forced_item["evidence_score"] = 5 if len(trusted_urls) >= 2 else 4
        forced_item["selection_reason"] = (
            "Deterministic priority inclusion: verified multi-lab frontier AI safety/governance "
            f"development omitted by model selection. {signal.reason}"
        )
        added_items.append(forced_item)
        decision["action"] = "included"

    result_edition = dict(edition)
    result_edition["items"] = selected_items + added_items

    record = {
        "category": PRIORITY_CATEGORY,
        "flagged_count": sum(1 for s in signals if s.flagged),
        "included_ids": [item.get("id") for item in added_items],
        "decisions": decisions,
    }
    return result_edition, record
