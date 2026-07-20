import csv
import json
from pathlib import Path

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        RESULTS_DIR,
        DETECTED_ROIS_PATH,
        REFERENCE_REGISTRY_PATH,
        INSPECTION_PROFILES_PATH,
        INSPECTION_RESULTS_PATH,
    )
except ModuleNotFoundError:
    from path_config import (
        RESULTS_DIR,
        DETECTED_ROIS_PATH,
        REFERENCE_REGISTRY_PATH,
        INSPECTION_PROFILES_PATH,
        INSPECTION_RESULTS_PATH,
    )


# ============================================================
# Input / Output Paths
# ============================================================

SSIM_RESULTS_PATH = RESULTS_DIR / "ssim_results.json"
OCR_RESULTS_PATH = RESULTS_DIR / "ocr_results.json"
INSPECTION_SUMMARY_CSV_PATH = RESULTS_DIR / "inspection_summary.csv"


# ============================================================
# Loaders
# ============================================================


def load_json(path: Path, name: str):
    if not path.exists():
        raise FileNotFoundError(
            f"{name} 파일이 없습니다: {path}\n" "이전 단계를 먼저 실행하세요."
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_registry():
    if not REFERENCE_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"reference_registry.csv 파일이 없습니다: {REFERENCE_REGISTRY_PATH}"
        )

    registry = {}

    with open(REFERENCE_REGISTRY_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            file_name = row.get("file_name", "").strip()
            if file_name:
                registry[file_name] = row

    return registry


# ============================================================
# Text / Rule Helpers
# ============================================================


def get_ocr_compare(ocr_roi: dict) -> dict:
    if not ocr_roi:
        return {
            "ocr_compare_status": "MISSING",
            "ocr_compare_reason": "OCR result missing",
            "reference_text_compact": "",
            "capture_text_compact": "",
            "reference_numbers": [],
            "capture_numbers": [],
            "number_match": False,
            "compact_match": False,
            "exact_match": False,
        }

    return ocr_roi.get("ocr_compare", {})


def is_loading_like_screen(category: str, memo: str, ocr_item: dict) -> bool:
    """
    로딩/처리 중 화면은 spinner 회전, 위치 차이 때문에 SSIM이 낮게 나올 수 있다.
    이런 화면은 SSIM FAIL만으로 최종 FAIL을 주지 않는다.
    """

    text_pool = f"{category} {memo}".lower()

    keywords = [
        "loading",
        "spinner",
        "로딩",
        "처리",
        "처리 중",
        "저장",
        "儲存",
        "保存",
        "行程清單",
    ]

    for keyword in keywords:
        if keyword.lower() in text_pool:
            return True

    # OCR 결과 안에도 로딩/저장 계열 문구가 있으면 로딩성 화면으로 판단
    if ocr_item:
        for roi in ocr_item.get("roi_results", []):
            compare = roi.get("ocr_compare", {})
            ref_text = compare.get("reference_text_compact", "")
            cap_text = compare.get("capture_text_compact", "")
            combined = f"{ref_text} {cap_text}".lower()

            for keyword in keywords:
                if keyword.lower() in combined:
                    return True

    return False


def has_number_mismatch(ocr_compare: dict) -> bool:
    ref_numbers = ocr_compare.get("reference_numbers", [])
    cap_numbers = ocr_compare.get("capture_numbers", [])

    if not ref_numbers and not cap_numbers:
        return False

    if ref_numbers != cap_numbers:
        return True

    return False


def has_text_confirmed_different(ocr_compare: dict) -> bool:
    """
    OCR이 어느 정도 텍스트를 읽었고,
    공백 제거 후에도 reference/capture 내용이 다르면 텍스트 차이 후보로 본다.
    다만 OCR 자체가 불안정할 수 있으므로 최종에서는 REVIEW 또는 일부 조건에서 FAIL로 사용한다.
    """

    ref_text = ocr_compare.get("reference_text_compact", "")
    cap_text = ocr_compare.get("capture_text_compact", "")

    if not ref_text or not cap_text:
        return False

    return ref_text != cap_text


# ============================================================
# ROI Decision Logic
# ============================================================


def decide_one_roi(
    category: str,
    profile_name: str,
    profile_info: dict,
    memo: str,
    is_loading_like: bool,
    diff_roi: dict,
    ssim_roi: dict,
    ocr_roi: dict,
):
    """
    ROI 하나에 대한 판정.
    이 단계에서는 SSIM만으로 바로 FAIL을 내리지 않도록 설계한다.
    """

    roi_id = diff_roi.get("roi_id", "")
    area_ratio = float(diff_roi.get("area_ratio", 0.0) or 0.0)

    ssim_status = "MISSING"
    ssim_score = None

    if ssim_roi:
        ssim_status = ssim_roi.get("ssim_status", "MISSING")
        ssim_score = ssim_roi.get("ssim_score", None)

    ocr_compare = get_ocr_compare(ocr_roi)
    ocr_status = ocr_compare.get("ocr_compare_status", "MISSING")

    number_mismatch = has_number_mismatch(ocr_compare)
    text_different = has_text_confirmed_different(ocr_compare)

    fail_area_ratio = float(profile_info.get("fail_area_ratio", 0.03))
    roi_large_threshold = max(0.003, fail_area_ratio / 4)

    reasons = []

    # 1. 숫자/단위가 중요한 화면에서 숫자가 다르면 강한 FAIL
    if profile_info.get("use_numeric_check", False) and number_mismatch:
        reasons.append("숫자/단위 OCR 결과가 다름")
        return {
            "roi_id": roi_id,
            "roi_final_status": "FAIL",
            "roi_reason": reasons,
            "ssim_status": ssim_status,
            "ssim_score": ssim_score,
            "ocr_status": ocr_status,
            "area_ratio": area_ratio,
        }

    # 2. OCR이 명확히 PASS면 SSIM이 낮아도 바로 FAIL 금지
    if ocr_status == "PASS":
        if ssim_status == "FAIL":
            if is_loading_like:
                reasons.append(
                    "OCR 문구는 일치, 로딩/처리 중 화면의 위치 또는 spinner 차이로 판단"
                )
                return {
                    "roi_id": roi_id,
                    "roi_final_status": "PASS",
                    "roi_reason": reasons,
                    "ssim_status": ssim_status,
                    "ssim_score": ssim_score,
                    "ocr_status": ocr_status,
                    "area_ratio": area_ratio,
                }
            else:
                reasons.append("OCR 문구는 일치하지만 이미지 위치/구조 차이가 있음")
                return {
                    "roi_id": roi_id,
                    "roi_final_status": "REVIEW",
                    "roi_reason": reasons,
                    "ssim_status": ssim_status,
                    "ssim_score": ssim_score,
                    "ocr_status": ocr_status,
                    "area_ratio": area_ratio,
                }

        reasons.append("OCR 문구 일치")
        return {
            "roi_id": roi_id,
            "roi_final_status": "PASS",
            "roi_reason": reasons,
            "ssim_status": ssim_status,
            "ssim_score": ssim_score,
            "ocr_status": ocr_status,
            "area_ratio": area_ratio,
        }

    # 3. OCR이 텍스트 차이를 의심하고, 텍스트 중심 화면이면 REVIEW 또는 FAIL
    if text_different:
        if category in {"text_list", "status_time", "setting_control"}:
            reasons.append("텍스트 중심 화면에서 OCR 텍스트 차이 감지")
            return {
                "roi_id": roi_id,
                "roi_final_status": "FAIL",
                "roi_reason": reasons,
                "ssim_status": ssim_status,
                "ssim_score": ssim_score,
                "ocr_status": ocr_status,
                "area_ratio": area_ratio,
            }
        else:
            reasons.append("OCR 텍스트 차이 후보 감지")
            return {
                "roi_id": roi_id,
                "roi_final_status": "REVIEW",
                "roi_reason": reasons,
                "ssim_status": ssim_status,
                "ssim_score": ssim_score,
                "ocr_status": ocr_status,
                "area_ratio": area_ratio,
            }

    # 4. OCR이 없거나 불확실한데 SSIM이 FAIL인 경우
    if ssim_status == "FAIL":
        if is_loading_like:
            reasons.append("로딩/처리 중 화면으로 판단되어 SSIM FAIL을 완화")
            return {
                "roi_id": roi_id,
                "roi_final_status": "REVIEW",
                "roi_reason": reasons,
                "ssim_status": ssim_status,
                "ssim_score": ssim_score,
                "ocr_status": ocr_status,
                "area_ratio": area_ratio,
            }

        if category in {"guide_image", "card_ui"} and area_ratio >= roi_large_threshold:
            reasons.append("이미지/카드 UI 영역에서 큰 시각적 차이 감지")
            return {
                "roi_id": roi_id,
                "roi_final_status": "FAIL",
                "roi_reason": reasons,
                "ssim_status": ssim_status,
                "ssim_score": ssim_score,
                "ocr_status": ocr_status,
                "area_ratio": area_ratio,
            }

        reasons.append("SSIM 기준 차이는 크지만 OCR 확인이 불충분함")
        return {
            "roi_id": roi_id,
            "roi_final_status": "REVIEW",
            "roi_reason": reasons,
            "ssim_status": ssim_status,
            "ssim_score": ssim_score,
            "ocr_status": ocr_status,
            "area_ratio": area_ratio,
        }

    # 5. SSIM이 REVIEW면 최종도 REVIEW
    if ssim_status == "REVIEW":
        reasons.append("SSIM 점수가 애매한 범위")
        return {
            "roi_id": roi_id,
            "roi_final_status": "REVIEW",
            "roi_reason": reasons,
            "ssim_status": ssim_status,
            "ssim_score": ssim_score,
            "ocr_status": ocr_status,
            "area_ratio": area_ratio,
        }

    # 6. OCR이 REVIEW인데 확실한 차이 근거가 없으면 REVIEW
    if ocr_status == "REVIEW":
        reasons.append("OCR 결과가 불확실함")
        return {
            "roi_id": roi_id,
            "roi_final_status": "REVIEW",
            "roi_reason": reasons,
            "ssim_status": ssim_status,
            "ssim_score": ssim_score,
            "ocr_status": ocr_status,
            "area_ratio": area_ratio,
        }

    # 7. 나머지는 PASS
    reasons.append("큰 이상 없음")
    return {
        "roi_id": roi_id,
        "roi_final_status": "PASS",
        "roi_reason": reasons,
        "ssim_status": ssim_status,
        "ssim_score": ssim_score,
        "ocr_status": ocr_status,
        "area_ratio": area_ratio,
    }


# ============================================================
# Item Decision Logic
# ============================================================


def decide_one_item(
    file_name: str,
    diff_item: dict,
    ssim_item: dict,
    ocr_item: dict,
    registry_row: dict,
    profiles: dict,
):
    screen_id = diff_item.get("screen_id", Path(file_name).stem)
    category = diff_item.get("category", registry_row.get("category", "general_diff"))
    profile_name = diff_item.get(
        "profile", registry_row.get("profile", "general_diff_profile")
    )
    memo = registry_row.get("memo", "")

    profile_info = profiles.get(profile_name, profiles.get("general_diff_profile", {}))

    diff_rois = diff_item.get("rois", [])
    ssim_rois = {
        roi.get("roi_id"): roi for roi in (ssim_item or {}).get("roi_results", [])
    }
    ocr_rois = {
        roi.get("roi_id"): roi for roi in (ocr_item or {}).get("roi_results", [])
    }

    diff_roi_count = int(diff_item.get("diff_roi_count", len(diff_rois)))
    total_diff_area_ratio = float(diff_item.get("total_diff_area_ratio", 0.0) or 0.0)
    fail_area_ratio = float(profile_info.get("fail_area_ratio", 0.03))

    loading_like = is_loading_like_screen(category, memo, ocr_item or {})

    roi_decisions = []

    for diff_roi in diff_rois:
        roi_id = diff_roi.get("roi_id")

        roi_decision = decide_one_roi(
            category=category,
            profile_name=profile_name,
            profile_info=profile_info,
            memo=memo,
            is_loading_like=loading_like,
            diff_roi=diff_roi,
            ssim_roi=ssim_rois.get(roi_id, {}),
            ocr_roi=ocr_rois.get(roi_id, {}),
        )

        roi_decisions.append(roi_decision)

    fail_count = sum(1 for r in roi_decisions if r["roi_final_status"] == "FAIL")
    review_count = sum(1 for r in roi_decisions if r["roi_final_status"] == "REVIEW")
    pass_count = sum(1 for r in roi_decisions if r["roi_final_status"] == "PASS")

    final_reasons = []

    if diff_roi_count == 0:
        final_status = "PASS"
        final_reasons.append("차이 ROI가 검출되지 않음")

    elif total_diff_area_ratio >= fail_area_ratio and not loading_like:
        severe_area_ratio = max(0.12, fail_area_ratio * 1.8)

        if total_diff_area_ratio >= severe_area_ratio:
            final_status = "FAIL"
            final_reasons.append(
                f"전체 차이 면적 비율이 매우 큼: {total_diff_area_ratio} >= {severe_area_ratio}"
            )
        else:
            final_status = "REVIEW"
            final_reasons.append(
                f"전체 차이 면적 비율이 기준을 초과했지만 OS/UI 위치 차이 가능성으로 REVIEW 처리: {total_diff_area_ratio} >= {fail_area_ratio}"
            )

    elif fail_count > 0:
        final_status = "FAIL"
        final_reasons.append(f"FAIL ROI {fail_count}개 존재")

    elif review_count > 0:
        final_status = "REVIEW"
        final_reasons.append(f"REVIEW ROI {review_count}개 존재")

    else:
        final_status = "PASS"
        final_reasons.append("검출된 ROI가 모두 허용 범위")

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": category,
        "profile": profile_name,
        "reference_image": diff_item.get("reference_image", ""),
        "capture_image": diff_item.get("capture_image", ""),
        "expected_result": registry_row.get("expected_result", "UNKNOWN"),
        "memo": memo,
        "is_loading_like": loading_like,
        "final_status": final_status,
        "final_reasons": final_reasons,
        "diff_summary": {
            "diff_roi_count": diff_roi_count,
            "total_diff_area_ratio": total_diff_area_ratio,
            "fail_area_ratio_threshold": fail_area_ratio,
        },
        "roi_decision_summary": {
            "pass_count": pass_count,
            "review_count": review_count,
            "fail_count": fail_count,
        },
        "roi_decisions": roi_decisions,
        "debug_images": {
            "diff_debug": diff_item.get("debug_image", ""),
        },
    }


# ============================================================
# Main
# ============================================================


def run_decision_engine():
    detected_rois = load_json(DETECTED_ROIS_PATH, "detected_rois.json")
    ssim_results = load_json(SSIM_RESULTS_PATH, "ssim_results.json")
    ocr_results = load_json(OCR_RESULTS_PATH, "ocr_results.json")
    inspection_profiles = load_json(
        INSPECTION_PROFILES_PATH, "inspection_profiles.json"
    )
    registry = load_reference_registry()

    diff_items = detected_rois.get("results", {})
    ssim_items = ssim_results.get("results", {})
    ocr_items = ocr_results.get("results", {})
    profiles = inspection_profiles.get("profiles", {})

    results = {}
    errors = []

    for idx, (file_name, diff_item) in enumerate(sorted(diff_items.items()), start=1):
        print(f"[{idx:03d}/{len(diff_items)}] Deciding {file_name}")

        try:
            item_result = decide_one_item(
                file_name=file_name,
                diff_item=diff_item,
                ssim_item=ssim_items.get(file_name, {}),
                ocr_item=ocr_items.get(file_name, {}),
                registry_row=registry.get(file_name, {}),
                profiles=profiles,
            )

            results[file_name] = item_result

        except Exception as e:
            errors.append(
                {
                    "file_name": file_name,
                    "error": str(e),
                }
            )
            print(f"  ERROR: {e}")

    pass_count = sum(1 for item in results.values() if item["final_status"] == "PASS")
    review_count = sum(
        1 for item in results.values() if item["final_status"] == "REVIEW"
    )
    fail_count = sum(1 for item in results.values() if item["final_status"] == "FAIL")

    summary = {
        "total_items": len(diff_items),
        "processed_count": len(results),
        "error_count": len(errors),
        "pass_count": pass_count,
        "review_count": review_count,
        "fail_count": fail_count,
        "errors": errors,
    }

    output = {
        "summary": summary,
        "results": results,
    }

    INSPECTION_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(INSPECTION_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    save_summary_csv(results)

    return output


def save_summary_csv(results: dict):
    fieldnames = [
        "screen_id",
        "file_name",
        "category",
        "profile",
        "expected_result",
        "final_status",
        "diff_roi_count",
        "pass_roi_count",
        "review_roi_count",
        "fail_roi_count",
        "total_diff_area_ratio",
        "is_loading_like",
        "memo",
        "final_reasons",
    ]

    with open(INSPECTION_SUMMARY_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for item in results.values():
            writer.writerow(
                {
                    "screen_id": item["screen_id"],
                    "file_name": item["file_name"],
                    "category": item["category"],
                    "profile": item["profile"],
                    "expected_result": item["expected_result"],
                    "final_status": item["final_status"],
                    "diff_roi_count": item["diff_summary"]["diff_roi_count"],
                    "pass_roi_count": item["roi_decision_summary"]["pass_count"],
                    "review_roi_count": item["roi_decision_summary"]["review_count"],
                    "fail_roi_count": item["roi_decision_summary"]["fail_count"],
                    "total_diff_area_ratio": item["diff_summary"][
                        "total_diff_area_ratio"
                    ],
                    "is_loading_like": item["is_loading_like"],
                    "memo": item["memo"],
                    "final_reasons": " | ".join(item["final_reasons"]),
                }
            )


def print_summary(output: dict):
    summary = output["summary"]

    print("\n========== DECISION ENGINE SUMMARY ==========")
    print(f"Total items     : {summary['total_items']}")
    print(f"Processed count : {summary['processed_count']}")
    print(f"Error count     : {summary['error_count']}")
    print("---------------------------------------------")
    print(f"PASS count      : {summary['pass_count']}")
    print(f"REVIEW count    : {summary['review_count']}")
    print(f"FAIL count      : {summary['fail_count']}")
    print("---------------------------------------------")
    print(f"Saved JSON      : {INSPECTION_RESULTS_PATH}")
    print(f"Saved CSV       : {INSPECTION_SUMMARY_CSV_PATH}")
    print("=============================================")


def main():
    output = run_decision_engine()
    print_summary(output)


if __name__ == "__main__":
    main()
