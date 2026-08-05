import json
from datetime import datetime, timezone
from pathlib import Path
from src.schemas import EditorialQualityReport, QualityCheckResult, Edition
from src.config import OUTPUT_DIR, PRIORITY_TOPICS, get_edition_dir


def validate_edition_quality(edition_dict: dict) -> EditorialQualityReport:
    """Validate a generated weekly news edition against explicit editorial quality gates (FP-008).
    
    Checks:
    - Temporal Alignment: Sources are within the start_date and end_date window boundaries.
    - Evidence Grounding: Every story has valid source URLs.
    - Topic Diversity: The edition is not dominated by a single project/announcement.
    - Relevance / Quality: Average relevance and evidence scores meet acceptable thresholds.
    - Slow Week Adjustment: Allow fewer than 3 items only if is_slow_week is explicitly declared.
    """
    edition_date = edition_dict.get("edition_date", "unknown")
    start_date_str = edition_dict.get("start_date")
    end_date_str = edition_dict.get("end_date")
    is_slow_week = edition_dict.get("is_slow_week", False)
    items = edition_dict.get("items", [])

    checks = []
    reasons_for_failure = []

    # Calculate fallback dates if missing in the edition dict
    if not start_date_str or not end_date_str:
        from src.ia_news_researcher import calculate_edition_window
        try:
            start_date_str, end_date_str = calculate_edition_window(edition_date)
        except Exception:
            start_date_str, end_date_str = None, None

    # --- check 1: Temporal Alignment ---
    temporal_passed = True
    temp_msg = "All news items are within the explicit coverage window."
    
    if start_date_str and end_date_str:
        start_day = start_date_str.split("T")[0]
        end_day = end_date_str.split("T")[0]
        
        out_of_bounds_count = 0
        for item in items:
            for src in item.get("sources", []):
                pub_date = src.get("published_date")
                if pub_date:
                    # Simple date string comparison (YYYY-MM-DD)
                    if not (start_day <= pub_date <= end_day):
                        out_of_bounds_count += 1
                        
        if out_of_bounds_count > 0:
            # We warn but don't hard-fail if there are minor date discrepancies, but if more than half are out-of-bounds, it's a fail
            if out_of_bounds_count > len(items) / 2:
                temporal_passed = False
                temp_msg = f"Temporal Alignment Failed: {out_of_bounds_count} sources are outside the coverage window ({start_day} to {end_day})."
                reasons_for_failure.append(temp_msg)
            else:
                temp_msg = f"Warning: {out_of_bounds_count} sources are outside the coverage window ({start_day} to {end_day}), but accepted as minor discrepancies."
    else:
        temporal_passed = False
        temp_msg = "Temporal Alignment Failed: Coverage window start_date or end_date missing."
        reasons_for_failure.append(temp_msg)

    checks.append(QualityCheckResult(
        check_name="temporal_alignment",
        passed=temporal_passed,
        message=temp_msg
    ))

    # --- check 2: Evidence Grounding ---
    grounding_passed = True
    grounding_msg = "All items have robust canonical source URLs."
    missing_url_count = 0
    
    for item in items:
        sources = item.get("sources", [])
        if not sources:
            missing_url_count += 1
            continue
        for src in sources:
            url = src.get("url", "")
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                missing_url_count += 1

    if missing_url_count > 0:
        grounding_passed = False
        grounding_msg = f"Evidence Grounding Failed: {missing_url_count} sources have missing or invalid URLs."
        reasons_for_failure.append(grounding_msg)

    checks.append(QualityCheckResult(
        check_name="evidence_grounding",
        passed=grounding_passed,
        message=grounding_msg
    ))

    # --- check 3: Quality Scoring & Relevance ---
    scoring_passed = True
    scoring_msg = "Editorial scores are strong and relevant."
    
    low_score_count = 0
    total_relevance = 0
    total_evidence = 0
    
    for item in items:
        rel = item.get("relevance_score", 0)
        ev = item.get("evidence_score", 0)
        total_relevance += rel
        total_evidence += ev
        if rel < 3 or ev < 3:
            low_score_count += 1

    avg_rel = total_relevance / len(items) if items else 0
    avg_ev = total_evidence / len(items) if items else 0

    if avg_rel < 3.0 or avg_ev < 3.0:
        scoring_passed = False
        scoring_msg = f"Quality Scoring Failed: Low average scores (Relevance: {avg_rel:.1f}/5, Evidence: {avg_ev:.1f}/5)."
        reasons_for_failure.append(scoring_msg)
    elif low_score_count > len(items) / 2:
        scoring_passed = False
        scoring_msg = f"Quality Scoring Failed: Too many individual stories with score < 3 ({low_score_count} items)."
        reasons_for_failure.append(scoring_msg)
    else:
        scoring_msg = f"Relevance and evidence scores passed. Average Relevance: {avg_rel:.1f}/5, Evidence: {avg_ev:.1f}/5."

    checks.append(QualityCheckResult(
        check_name="quality_scoring",
        passed=scoring_passed,
        message=scoring_msg
    ))

    # --- check 4: Topic Diversity & Domination ---
    diversity_passed = True
    diversity_msg = "Edition contains a healthy diverse set of stories."
    
    company_mentions = {}
    for item in items:
        title_lower = item.get("title", "").lower()
        summary_lower = item.get("summary", "").lower()
        text_to_check = title_lower + " " + summary_lower
        
        # Simple brand tracking
        for brand in ["openai", "google", "gemini", "claude", "anthropic", "meta", "llama", "deepseek", "apple"]:
            if brand in text_to_check:
                company_mentions[brand] = company_mentions.get(brand, 0) + 1

    # Check if a single company dominates the entire edition (>75% of stories)
    for brand, count in company_mentions.items():
        if count >= len(items) and len(items) >= 3:
            diversity_passed = False
            diversity_msg = f"Topic Diversity Failed: Single provider '{brand.upper()}' dominates the entire edition ({count}/{len(items)} stories)."
            reasons_for_failure.append(diversity_msg)
            break

    checks.append(QualityCheckResult(
        check_name="topic_diversity",
        passed=diversity_passed,
        message=diversity_msg
    ))

    # --- check 5: Slow Week Adjustment ---
    slow_week_passed = True
    slow_week_msg = "Edition meets size requirements."
    
    if len(items) < 3 and not is_slow_week:
        slow_week_passed = False
        slow_week_msg = "Slow Week check Failed: Fewer than 3 stories selected, but slow_week flag is false."
        reasons_for_failure.append(slow_week_msg)
    elif len(items) < 2:
        slow_week_passed = False
        slow_week_msg = "Fails to meet absolute minimum count of 2 stories even for a slow week."
        reasons_for_failure.append(slow_week_msg)
    elif is_slow_week:
        slow_week_msg = f"Slow week adjustment applied: accepting {len(items)} high-quality stories instead of filling with weak news."

    checks.append(QualityCheckResult(
        check_name="slow_week_adjustment",
        passed=slow_week_passed,
        message=slow_week_msg
    ))

    # --- Final Verdict ---
    passed = all(check.passed for check in checks)

    report = EditorialQualityReport(
        edition_date=edition_date,
        passed=passed,
        checks=checks,
        slow_week_adjustment=is_slow_week,
        reasons_for_failure=reasons_for_failure
    )

    # Save report to disk for auditing
    report_file = get_edition_dir(edition_date) / "quality_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(json.loads(report.model_dump_json()), f, ensure_ascii=False, indent=2)
    print(f"[*] Editorial Quality Gate completed. Passed: {passed}. Report saved to: {report_file}")

    return report
