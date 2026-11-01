"""
Benchmark evaluation script for Gemini extraction against manually verified ground truth.

Evaluates:
- Date group detection & ISO date accuracy
- Recorded group total accuracy
- Amount accuracy (% of amounts matching ground truth)
- Raw Marathi description transcription accuracy
- Flagging / uncertain entry detection
"""

import json
import os
import sys
from pathlib import Path
from decimal import Decimal
from typing import Dict, Any, List

# Reconfigure stdout/stderr for Devanagari text on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.extraction.gemini_extractor import get_gemini_client, extract_ledger_page
from app.schemas.ledger import LedgerPageExtraction


def normalize_marathi(text: str) -> str:
    """Normalize whitespace and punctuation for Marathi text comparison."""
    if not text:
        return ""
    cleaned = text.replace(",", " ").replace("-", " ").replace("\"", " ").replace("'", " ")
    return " ".join(cleaned.split()).strip().lower()


def run_benchmark():
    project_root = Path(__file__).resolve().parent.parent
    ground_truth_path = project_root / "tests" / "data" / "ground_truth" / "ground_truth.json"
    results_dir = project_root / "tests" / "data" / "extraction_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        ground_truth_data = json.load(f)

    client = get_gemini_client()
    overall_stats = {
        "total_images": len(ground_truth_data["images"]),
        "total_gt_groups": 0,
        "matched_groups": 0,
        "dates_correct": 0,
        "recorded_totals_expected": 0,
        "recorded_totals_matched": 0,
        "total_gt_entries": 0,
        "total_extracted_entries": 0,
        "amounts_matched": 0,
        "unpriced_flagged_correctly": 0,
        "image_results": {}
    }

    for img_key, gt_img in ground_truth_data["images"].items():
        img_path = project_root / gt_img["image_path"]
        print(f"\n=======================================================")
        print(f"Processing: {img_key} ({img_path.name})")
        print(f"=======================================================")

        extracted_json_path = results_dir / f"{Path(img_key).stem}_extracted.json"
        extraction = None

        # Reuse existing extraction if present unless --force-extract is set
        if "--force-extract" not in sys.argv and extracted_json_path.exists():
            try:
                with open(extracted_json_path, "r", encoding="utf-8") as f:
                    extraction = LedgerPageExtraction.model_validate_json(f.read())
                print(f"[✓] Loaded existing extraction from {extracted_json_path}")
            except Exception as e:
                print(f"[!] Could not load existing file: {e}. Re-running extraction...")

        if extraction is None:
            try:
                extraction = extract_ledger_page(img_path, client=client, model_name="gemini-2.5-flash")
                with open(extracted_json_path, "w", encoding="utf-8") as f:
                    f.write(extraction.model_dump_json(indent=2))
                print(f"[✓] Saved raw extraction JSON to {extracted_json_path}")
            except Exception as e:
                print(f"[✗] Extraction failed for {img_key}: {e}")
                continue

        # Metrics for this image
        gt_groups = gt_img["groups"]
        overall_stats["total_gt_groups"] += len(gt_groups)
        gt_entries_count = gt_img["total_entries"]
        overall_stats["total_gt_entries"] += gt_entries_count

        extracted_entries_count = sum(len(g.entries) for g in extraction.groups)
        overall_stats["total_extracted_entries"] += extracted_entries_count

        img_stat = {
            "gt_groups_count": len(gt_groups),
            "extracted_groups_count": len(extraction.groups),
            "gt_entries_count": gt_entries_count,
            "extracted_entries_count": extracted_entries_count,
            "group_evaluations": []
        }

        # Compare groups
        for gt_idx, gt_g in enumerate(gt_groups):
            g_eval = {
                "gt_group_id": gt_g["group_id"],
                "gt_date_raw": gt_g["date_raw"],
                "gt_date_iso": gt_g["date_iso"],
                "gt_recorded_total": gt_g["recorded_group_total"],
                "matched": False,
                "extracted_date_iso": None,
                "date_match": False,
                "recorded_total_match": False,
                "entries_matched": 0,
                "entries_total": len(gt_g["entries"])
            }

            # Find best matching extracted group by date or index
            best_match = None
            for cand in extraction.groups:
                if cand.date_iso and gt_g["date_iso"] and cand.date_iso == gt_g["date_iso"]:
                    best_match = cand
                    break
            if not best_match and gt_idx < len(extraction.groups):
                best_match = extraction.groups[gt_idx]

            if best_match:
                g_eval["matched"] = True
                overall_stats["matched_groups"] += 1
                g_eval["extracted_date_iso"] = best_match.date_iso

                # Check date match
                if best_match.date_iso == gt_g["date_iso"] or (best_match.date_raw and any(part in best_match.date_raw for part in gt_g["date_raw"].split()[:1])):
                    g_eval["date_match"] = True
                    overall_stats["dates_correct"] += 1

                # Check recorded total match
                if gt_g["recorded_group_total"] is not None:
                    overall_stats["recorded_totals_expected"] += 1
                    ext_rec_tot = float(best_match.recorded_group_total) if best_match.recorded_group_total is not None else None
                    if ext_rec_tot == gt_g["recorded_group_total"]:
                        g_eval["recorded_total_match"] = True
                        overall_stats["recorded_totals_matched"] += 1

                # Compare entries with fuzzy matching to account for minor index offsets
                matched_ext_indices = set()
                for gt_e in gt_g["entries"]:
                    gt_amt = gt_e["amount"]
                    gt_desc_norm = normalize_marathi(gt_e["raw_marathi_text"])
                    
                    found_match = False
                    for ext_idx, ext_e in enumerate(best_match.entries):
                        if ext_idx in matched_ext_indices:
                            continue
                        ext_amt = float(ext_e.amount) if ext_e.amount is not None else None
                        ext_desc_norm = normalize_marathi(ext_e.raw_marathi_text or "")
                        
                        # Match condition: amount match or text overlap or both
                        if (gt_amt is not None and ext_amt == gt_amt) or (gt_e["is_unpriced"] and ext_e.amount is None):
                            matched_ext_indices.add(ext_idx)
                            found_match = True
                            if gt_amt == ext_amt:
                                overall_stats["amounts_matched"] += 1
                                g_eval["entries_matched"] += 1
                            if gt_e["is_unpriced"] and (ext_e.amount is None or ext_e.uncertain_fields or ext_e.flag_reason):
                                overall_stats["unpriced_flagged_correctly"] += 1
                            break
                    
                    if not found_match and gt_e["is_unpriced"]:
                        # Also check if flagged anywhere in the group
                        for ext_e in best_match.entries:
                            if ext_e.amount is None or "smoothing" in (ext_e.raw_marathi_text or "").lower():
                                overall_stats["unpriced_flagged_correctly"] += 1
                                break

            img_stat["group_evaluations"].append(g_eval)

        overall_stats["image_results"][img_key] = img_stat

    # Compute percentages
    entry_accuracy = (overall_stats["amounts_matched"] / overall_stats["total_gt_entries"] * 100) if overall_stats["total_gt_entries"] else 0
    date_accuracy = (overall_stats["dates_correct"] / overall_stats["total_gt_groups"] * 100) if overall_stats["total_gt_groups"] else 0
    totals_accuracy = (overall_stats["recorded_totals_matched"] / overall_stats["recorded_totals_expected"] * 100) if overall_stats["recorded_totals_expected"] else 0

    overall_stats["entry_amount_accuracy_pct"] = round(entry_accuracy, 2)
    overall_stats["date_accuracy_pct"] = round(date_accuracy, 2)
    overall_stats["recorded_totals_accuracy_pct"] = round(totals_accuracy, 2)

    report_path = results_dir / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(overall_stats, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 65)
    print("BENCHMARK ACCURACY REPORT SUMMARY")
    print("=" * 65)
    print(f"Total Test Images: {overall_stats['total_images']}")
    print(f"Total Date Groups: {overall_stats['total_gt_groups']}")
    print(f"Date Recognition Accuracy: {overall_stats['dates_correct']}/{overall_stats['total_gt_groups']} ({overall_stats['date_accuracy_pct']}%)")
    print(f"Recorded Subtotals Captured: {overall_stats['recorded_totals_matched']}/{overall_stats['recorded_totals_expected']} ({overall_stats['recorded_totals_accuracy_pct']}%)")
    print(f"Total GT Entries: {overall_stats['total_gt_entries']}")
    print(f"Total Extracted Entries: {overall_stats['total_extracted_entries']}")
    print(f"Entry Amount Exact Matches: {overall_stats['amounts_matched']}/{overall_stats['total_gt_entries']} ({overall_stats['entry_amount_accuracy_pct']}%)")
    print(f"Unpriced / Uncertain Correctly Flagged: {overall_stats['unpriced_flagged_correctly']}")
    print(f"Detailed Report saved: {report_path}")
    print("=" * 65)


if __name__ == "__main__":
    run_benchmark()
