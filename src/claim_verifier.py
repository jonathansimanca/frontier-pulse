"""Edition-level claim check for Frontier Pulse.

Discovery summaries are written by Gemini and can overstate what sources report (for example,
attributing an endorsement to people who never made it). After selection, a single grounded
Gemini call verifies the selected stories and returns corrected text for any unsupported claim.

The check is deliberately conservative:
- One call for the whole edition; no retries.
- Corrections are applied only when the call was grounded in Google Search, and only for
  claims that a found source contradicts, with that source URL as evidence. Claims the model
  merely could not find are kept, because an unverifiable claim is not necessarily false.
- Only ``title``, ``summary``, ``why_it_matters`` and ``key_takeaways`` may change. Ids, sources,
  scores, and the set of stories never change.
- Any failure (API error, unparseable output, invalid correction, schema validation) keeps the
  original text, so the claim check can never block an edition.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from google.genai import types

from src.research_audit import extract_grounding_metadata
from src.schemas import Edition

TEXT_FIELDS = ("title", "summary", "why_it_matters")
CLAIM_CHECK_FIELDS = TEXT_FIELDS + ("key_takeaways",)
MAX_REMOVED_CLAIMS = 10
MAX_CLAIM_CHARS = 300


def build_claim_check_prompt(news_data: dict) -> str:
    """Build the single fact-checking prompt for all selected stories in an edition."""
    stories = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "why_it_matters": item.get("why_it_matters"),
            "key_takeaways": item.get("key_takeaways", []),
            "sources": [
                {"url": src.get("url"), "publisher": src.get("publisher"), "published_date": src.get("published_date")}
                for src in item.get("sources", [])
            ],
        }
        for item in news_data.get("items", [])
    ]
    stories_json = json.dumps(stories, ensure_ascii=False, indent=2)

    return f"""
You are the FACT-CHECK EDITOR for the 'Frontier Pulse' podcast, edition {news_data.get('edition_date')}.
Use Google Search to verify the factual claims in each story below against its cited sources and reputable reporting.

RULES:
1. Search for each story. Check names of people and organizations, who said, endorsed, or committed to what, numbers, dates, and product names.
2. Correct or remove a claim ONLY when a source you found contradicts it (for example, a person is reported as endorsing something that reputable reporting says they did not). For every removed or changed claim, give the URL of that contradicting source as evidence_url.
3. Do NOT remove a claim just because you could not find it. If you cannot confirm or contradict a claim, keep it and do not mark the story as corrected.
4. Keep verified content and the story's subject. Do not add new facts beyond what your sources report.
5. Keep the original language and a similar length. key_takeaways must contain 1 to 5 items.
6. If no claim in a story is contradicted, return verdict "supported" and omit its text fields.

STORIES:
{stories_json}

OUTPUT: return ONLY raw JSON inside ```json and ``` with this shape:
```json
{{
  "items": [
    {{
      "id": "story id exactly as given",
      "verdict": "supported or corrected",
      "title": "corrected title (only when corrected)",
      "summary": "corrected summary (only when corrected)",
      "why_it_matters": "corrected text (only when corrected)",
      "key_takeaways": ["corrected takeaway (only when corrected)"],
      "removed_claims": [
        {{"claim": "the contradicted claim you removed or changed", "evidence_url": "https://source-that-contradicts-it"}}
      ]
    }}
  ]
}}
```
""".strip()


def _valid_removed_claims(entry: dict) -> tuple[list[dict], str | None]:
    """Return normalized removed claims, or an error when any claim lacks contradiction evidence."""
    removed = entry.get("removed_claims")
    if not isinstance(removed, list) or not removed:
        return [], "Correction has no removed_claims with evidence."
    normalized = []
    for claim in removed[:MAX_REMOVED_CLAIMS]:
        if not isinstance(claim, dict):
            return [], "Each removed claim must be an object with 'claim' and 'evidence_url'."
        text = claim.get("claim")
        url = claim.get("evidence_url")
        if not isinstance(text, str) or not text.strip():
            return [], "A removed claim has no text."
        if not isinstance(url, str) or not url.strip().lower().startswith(("http://", "https://")):
            return [], "A removed claim has no valid evidence_url."
        normalized.append({"claim": text.strip()[:MAX_CLAIM_CHARS], "evidence_url": url.strip()})
    return normalized, None


def _valid_correction(entry: dict) -> tuple[dict, str | None]:
    """Return the valid corrected fields of an entry, or an error note when any field is invalid."""
    corrected: dict[str, Any] = {}
    for field in TEXT_FIELDS:
        if field in entry:
            value = entry[field]
            if not isinstance(value, str) or not value.strip():
                return {}, f"Invalid '{field}' in correction."
            corrected[field] = value.strip()
    if "key_takeaways" in entry:
        takeaways = entry["key_takeaways"]
        if (
            not isinstance(takeaways, list)
            or not 1 <= len(takeaways) <= 5
            or not all(isinstance(t, str) and t.strip() for t in takeaways)
        ):
            return {}, "Invalid 'key_takeaways' in correction."
        corrected["key_takeaways"] = [t.strip() for t in takeaways]
    return corrected, None


def apply_claim_corrections(news_data: dict, payload: Any) -> tuple[dict, list[dict], list[str]]:
    """Apply a claim-check payload to an edition without mutating the input.

    Returns ``(edition, item_records, ignored_ids)``. Each item record has ``id``, ``verdict``
    (``supported``, ``corrected``, ``not_checked`` or ``invalid_correction``),
    ``changed_fields``, ``removed_claims`` (``{claim, evidence_url}`` objects) and ``note``.
    A correction is applied only when every removed claim carries an evidence URL.
    """
    entries = payload.get("items", []) if isinstance(payload, dict) else []
    entries_by_id = {e.get("id"): e for e in entries if isinstance(e, dict) and e.get("id")}
    edition_ids = {item.get("id") for item in news_data.get("items", [])}
    ignored_ids = sorted(str(i) for i in entries_by_id if i not in edition_ids)

    new_items: list[dict] = []
    records: list[dict] = []
    for item in news_data.get("items", []):
        entry = entries_by_id.get(item.get("id"))
        record = {"id": item.get("id"), "verdict": "not_checked", "changed_fields": [], "removed_claims": [], "note": None}
        new_item = dict(item)

        if entry is not None:
            verdict = str(entry.get("verdict", "supported")).strip().lower()
            if verdict != "corrected":
                record["verdict"] = "supported"
            else:
                removed_claims, evidence_error = _valid_removed_claims(entry)
                corrected, error = _valid_correction(entry)
                error = evidence_error or error
                if not error:
                    record["removed_claims"] = removed_claims
                if error:
                    record["verdict"] = "invalid_correction"
                    record["note"] = f"{error} Original text kept."
                else:
                    changed = [f for f in CLAIM_CHECK_FIELDS if f in corrected and corrected[f] != item.get(f)]
                    for field in changed:
                        new_item[field] = corrected[field]
                    record["verdict"] = "corrected"
                    record["changed_fields"] = changed

        new_items.append(new_item)
        records.append(record)

    result = dict(news_data)
    result["items"] = new_items
    return result, records, ignored_ids


def verify_edition_claims(client: Any, news_data: dict, model: str, enabled: bool = True) -> tuple[dict, dict]:
    """Run the single grounded claim check and return ``(edition, audit_record)``.

    The returned edition is the corrected edition on success, or the original edition when the
    check is disabled or fails for any reason.
    """
    record: dict[str, Any] = {
        "status": "skipped",
        "model": model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 0,
        "grounded": None,
        "web_search_queries": [],
        "error": None,
        "parse_strategy": None,
        "parse_repairs": None,
        "raw_response": None,
        "ignored_ids": [],
        "items": [],
    }
    if not enabled:
        record["error"] = "Claim check disabled by configuration."
        return news_data, record

    # Imported lazily: ia_news_researcher imports this module.
    from src.ia_news_researcher import parse_json_with_diagnostics

    started = time.monotonic()
    try:
        response = client.models.generate_content(
            model=model,
            contents=build_claim_check_prompt(news_data),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.1,
            ),
        )
        queries, sources = extract_grounding_metadata(response)
        record["web_search_queries"] = queries
        record["grounded"] = bool(queries or sources)
        if not record["grounded"]:
            record["raw_response"] = response.text
            record["status"] = "unverified_no_search"
            record["error"] = "Claim check returned no grounding metadata; no corrections applied."
            record["items"] = [
                {"id": item.get("id"), "verdict": "unverified_no_search", "changed_fields": [], "removed_claims": [], "note": None}
                for item in news_data.get("items", [])
            ]
            return news_data, record
        record["raw_response"] = response.text
        payload, diagnostics = parse_json_with_diagnostics(response.text)
        record["parse_strategy"] = diagnostics["strategy"]
        record["parse_repairs"] = diagnostics["repairs"]
        corrected_edition, item_records, ignored_ids = apply_claim_corrections(news_data, payload)
        validated = Edition.model_validate(corrected_edition)
        record.update(status="success", items=item_records, ignored_ids=ignored_ids)
        result = json.loads(validated.model_dump_json())
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"[:500]
        result = news_data
    finally:
        record["duration_ms"] = int((time.monotonic() - started) * 1000)

    corrected_ids = [r["id"] for r in record["items"] if r["verdict"] == "corrected" and r["changed_fields"]]
    if record["status"] == "success":
        print(f"[+] Claim check completed: {len(corrected_ids)} story(ies) corrected {corrected_ids}.")
    else:
        print(f"[!] Warning: Claim check did not verify the edition; original story text kept. {record['error']}")
    return result, record
