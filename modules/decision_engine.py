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


def normalize_text_for_judgement(text: str) -> str:
    """
    사람이 봤을 때 의미 차이가 거의 없는 요소를 제거한다.
    띄어쓰기, 줄바꿈, 일부 구두점 차이는 FAIL 근거로 쓰지 않는다.
    """
    if not text:
        return ""

    remove_chars = [
        " ",
        "\t",
        "\n",
        "\r",
        "　",
        ".",
        ",",
        "，",
        "。",
        "、",
        ":",
        "：",
        ";",
        "；",
        "-",
        "–",
        "—",
        "_",
    ]

    normalized = str(text)

    for ch in remove_chars:
        normalized = normalized.replace(ch, "")

    return normalized.strip()


def has_text_confirmed_different(ocr_compare: dict) -> bool:
    """
    OCR이 읽은 텍스트가 의미상 다른지 판단한다.
    단순 띄어쓰기/구두점 차이는 FAIL 근거로 보지 않는다.
    """

    ref_text = ocr_compare.get("reference_text_compact", "")
    cap_text = ocr_compare.get("capture_text_compact", "")

    if not ref_text or not cap_text:
        return False

    ref_norm = normalize_text_for_judgement(ref_text)
    cap_norm = normalize_text_for_judgement(cap_text)

    if not ref_norm or not cap_norm:
        return False

    return ref_norm != cap_norm


def has_missing_text_candidate(ocr_roi: dict) -> bool:
    """
    기준 이미지에서는 OCR 텍스트가 어느 정도 읽히는데,
    비교 이미지에서는 텍스트가 거의 없거나 크게 줄어든 경우를 찾는다.

    파일명 기준이 아니라 '텍스트 누락 현상' 기준이다.
    """
    if not ocr_roi:
        return False

    ocr_compare = get_ocr_compare(ocr_roi)

    ref_text = normalize_text_for_judgement(
        ocr_compare.get("reference_text_compact", "")
    )
    cap_text = normalize_text_for_judgement(ocr_compare.get("capture_text_compact", ""))

    if not ref_text:
        return False

    # 너무 짧은 텍스트는 OCR 오탐 위험이 크므로 제외
    if len(ref_text) < 4:
        return False

    # 기준에는 텍스트가 있는데 비교 이미지에서 거의 사라진 경우
    if not cap_text:
        return True

    # 비교 텍스트 길이가 기준 대비 매우 짧아진 경우
    if len(cap_text) / max(len(ref_text), 1) <= 0.35:
        return True

    return False


def has_missing_text_confirmed(ocr_roi: dict, ssim_roi: dict) -> bool:
    """
    기준 화면의 텍스트가 검사 화면에서 명확히 누락된 경우만 찾는다.
    OCR 신뢰도, SSIM, ROI 면적을 함께 확인하여
    증기, 게이지, 작은 렌더링 차이를 누락으로 오인하지 않도록 한다.
    """
    if not ocr_roi or not ssim_roi:
        return False

    ocr_compare = get_ocr_compare(ocr_roi)

    reference_text = normalize_text_for_judgement(
        ocr_compare.get("reference_text_compact", "")
    )

    reference_confidence = float(
        ocr_roi.get("reference_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )

    capture_confidence = float(
        ocr_roi.get("capture_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )

    ssim_status = ssim_roi.get("ssim_status", "MISSING")

    area_ratio = float(ocr_roi.get("area_ratio", 0.0) or 0.0)

    return (
        len(reference_text) >= 4
        and reference_confidence >= 0.80
        and capture_confidence <= 0.40
        and ssim_status == "FAIL"
        and area_ratio >= 0.01
    )


def get_ocr_min_confidence(ocr_roi: dict) -> float:
    """
    reference/capture OCR 중 더 낮은 confidence를 반환한다.
    둘 중 하나라도 낮으면 OCR 비교를 확정 판정에 쓰기 어렵다.
    """
    if not ocr_roi:
        return 0.0

    reference_conf = float(
        ocr_roi.get("reference_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )
    capture_conf = float(
        ocr_roi.get("capture_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )

    return min(reference_conf, capture_conf)


def is_ocr_confident(ocr_roi: dict, threshold: float = 0.70) -> bool:
    """
    OCR 결과를 최종 FAIL 근거로 써도 될 만큼 신뢰도가 높은지 판단한다.
    """
    return get_ocr_min_confidence(ocr_roi) >= threshold


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
    핵심 원칙:
    - SSIM만으로 바로 FAIL을 남발하지 않는다.
    - OCR 신뢰도가 낮으면 FAIL이 아니라 REVIEW로 보낸다.
    - 숫자/단위 불일치가 OCR 신뢰도 높게 확인되면 FAIL.
    - guide_image/card_ui의 큰 시각 차이는 FAIL 후보.
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
    ocr_confidence_threshold = float(profile_info.get("ocr_confidence_review", 0.70))

    ocr_confident = is_ocr_confident(
        ocr_roi,
        threshold=ocr_confidence_threshold,
    )
    ocr_min_confidence = get_ocr_min_confidence(ocr_roi)

    fail_area_ratio = float(profile_info.get("fail_area_ratio", 0.03))
    roi_large_threshold = max(0.003, fail_area_ratio / 4)

    reasons = []

    # 1. 숫자/단위가 중요한 화면에서 숫자가 다르면 FAIL.
    # 단, OCR confidence가 낮으면 REVIEW로 보낸다.
    if profile_info.get("use_numeric_check", False) and number_mismatch:
        if ocr_confident:
            reasons.append("OCR 신뢰도 높은 숫자/단위 불일치")
            return {
                "roi_id": roi_id,
                "roi_final_status": "FAIL",
                "roi_reason": reasons,
                "ssim_status": ssim_status,
                "ssim_score": ssim_score,
                "ocr_status": ocr_status,
                "ocr_min_confidence": ocr_min_confidence,
                "area_ratio": area_ratio,
            }
        else:
            reasons.append("숫자/단위 차이 후보이나 OCR 신뢰도 낮음")
            return {
                "roi_id": roi_id,
                "roi_final_status": "REVIEW",
                "roi_reason": reasons,
                "ssim_status": ssim_status,
                "ssim_score": ssim_score,
                "ocr_status": ocr_status,
                "ocr_min_confidence": ocr_min_confidence,
                "area_ratio": area_ratio,
            }

    # 2. OCR이 명확히 PASS면 SSIM이 낮아도 바로 FAIL 금지
    if ocr_status == "PASS":
        if ssim_status == "FAIL":
            if is_loading_like:
                reasons.append(
                    "OCR 문구 일치, 로딩/처리 중 화면의 위치 또는 spinner 차이로 판단"
                )
                return {
                    "roi_id": roi_id,
                    "roi_final_status": "PASS",
                    "roi_reason": reasons,
                    "ssim_status": ssim_status,
                    "ssim_score": ssim_score,
                    "ocr_status": ocr_status,
                    "ocr_min_confidence": ocr_min_confidence,
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
                    "ocr_min_confidence": ocr_min_confidence,
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
            "ocr_min_confidence": ocr_min_confidence,
            "area_ratio": area_ratio,
        }

    # 3. OCR 텍스트가 다르게 읽힌 경우
    # OCR confidence가 충분히 높을 때만 FAIL 근거로 사용한다.
    if text_different:
        if category in {"text_list", "status_time", "setting_control"}:
            if ocr_confident:
                reasons.append("OCR 신뢰도 높은 텍스트 차이 감지")
                return {
                    "roi_id": roi_id,
                    "roi_final_status": "FAIL",
                    "roi_reason": reasons,
                    "ssim_status": ssim_status,
                    "ssim_score": ssim_score,
                    "ocr_status": ocr_status,
                    "ocr_min_confidence": ocr_min_confidence,
                    "area_ratio": area_ratio,
                }
            else:
                reasons.append("텍스트 차이 후보이나 OCR 신뢰도 낮음")
                return {
                    "roi_id": roi_id,
                    "roi_final_status": "REVIEW",
                    "roi_reason": reasons,
                    "ssim_status": ssim_status,
                    "ssim_score": ssim_score,
                    "ocr_status": ocr_status,
                    "ocr_min_confidence": ocr_min_confidence,
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
                "ocr_min_confidence": ocr_min_confidence,
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
                "ocr_min_confidence": ocr_min_confidence,
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
                "ocr_min_confidence": ocr_min_confidence,
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
            "ocr_min_confidence": ocr_min_confidence,
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
            "ocr_min_confidence": ocr_min_confidence,
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
            "ocr_min_confidence": ocr_min_confidence,
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
        "ocr_min_confidence": ocr_min_confidence,
        "area_ratio": area_ratio,
    }


def can_auto_pass_review_item(
    category: str,
    total_diff_area_ratio: float,
    diff_roi_count: int,
    fail_count: int,
    review_count: int,
    loading_like: bool,
):
    """
    REVIEW 항목 중 사람 기준 PASS에 가까운 항목만 자동 PASS로 내린다.

    원칙:
    - FAIL ROI가 있으면 자동 PASS 금지
    - guide_image는 자동 PASS 금지
    - status_time은 글자/숫자 누락 위험이 있어 매우 보수적으로 처리
    - card_ui, popup, 일부 text_list, 일부 setting_control은
    OS/UI 위치 차이와 렌더링 차이가 많이 생기므로 조건부 PASS 허용
    """

    if fail_count > 0:
        return False, "FAIL ROI가 있어 자동 PASS 불가"

    if review_count == 0:
        return False, "REVIEW ROI가 없어 자동 PASS 대상 아님"

    # 안내 그림 화면은 그림 자체 오류 위험이 크므로 자동 PASS 금지
    if category == "guide_image":
        return False, "안내 이미지 화면은 자동 PASS 금지"

    # popup은 사람이 봤을 때 통과 가능한 위치/렌더링 차이가 많음
    if category == "popup":
        if total_diff_area_ratio <= 0.02 and diff_roi_count <= 3:
            return True, "팝업 화면의 허용 가능한 위치/렌더링 차이로 자동 PASS"
        return False, "팝업 화면의 차이가 자동 PASS 기준보다 큼"

        # card_ui는 카드/버튼/아이콘 위치 차이가 많지만,
    # ROI 개수가 적은데 면적이 큰 경우는 글씨/사진 위치 차이일 수 있으므로 REVIEW로 남긴다.
    if category == "card_ui":
        # 작은 차이 1~2개만 있는 경우: 진짜 아주 작은 면적만 PASS
        if diff_roi_count <= 2:
            if total_diff_area_ratio <= 0.015:
                return True, "카드 UI의 매우 작은 단일 위치/렌더링 차이로 자동 PASS"
            return (
                False,
                "카드 UI에서 적은 ROI지만 면적이 커 글씨/사진 차이 가능성으로 REVIEW 유지",
            )

        # 여러 카드/버튼에 분산된 작은 렌더링 차이는 PASS 허용
        if diff_roi_count >= 6 and total_diff_area_ratio <= 0.05:
            return True, "카드 UI의 분산형 위치/렌더링 차이로 자동 PASS"

        # 중간 영역은 애매하므로 REVIEW
        return False, "카드 UI 차이가 자동 PASS 기준보다 큼"

    # text_list는 글자 내용 오류 위험이 있어 아주 작은 차이만 PASS
    if category == "text_list":
        if total_diff_area_ratio <= 0.012 and diff_roi_count <= 9:
            return True, "텍스트 목록 화면의 작은 렌더링/위치 차이로 자동 PASS"
        return False, "텍스트 목록 화면은 자동 PASS 기준보다 차이가 큼"

    # setting_control은 설정값 오류 위험이 있으므로 FAIL ROI 없는 분산형 UI 차이만 PASS
    if category == "setting_control":
        if total_diff_area_ratio <= 0.06 and diff_roi_count >= 8:
            return True, "설정 화면의 분산형 위치/렌더링 차이로 자동 PASS"
        return False, "설정 화면은 자동 PASS 기준에 해당하지 않음"

    # status_time은 숫자/상태 누락 위험이 있으므로
    # 전체 차이 면적이 매우 작고 FAIL ROI가 없는 경우만 자동 PASS
    if category == "status_time":
        if total_diff_area_ratio <= 0.015 and diff_roi_count <= 12:
            return (
                True,
                "상태/시간 화면의 전체 차이 면적이 매우 작아 "
                "글자 위치/렌더링 차이로 자동 PASS",
            )

        return (
            False,
            "상태/시간 화면은 숫자/상태 정보 오류 위험으로 " "자동 PASS 제한",
        )


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

    missing_text_count = sum(
        1 for roi in ocr_rois.values() if has_missing_text_candidate(roi)
    )
    confirmed_missing_text_count = sum(
        1
        for roi_id, ocr_roi in ocr_rois.items()
        if has_missing_text_confirmed(
            ocr_roi,
            ssim_rois.get(roi_id, {}),
        )
    )

    final_reasons = []

    if diff_roi_count == 0:
        final_status = "PASS"
        final_reasons.append("차이 ROI가 검출되지 않음")

    # 1. 안내 이미지 화면: 좌측/중앙 그림이 크게 다르면 FAIL
    elif (
        category == "guide_image"
        and total_diff_area_ratio >= 0.085
        and diff_roi_count >= 4
    ):
        final_status = "FAIL"
        final_reasons.append(
            f"안내 이미지 화면에서 큰 그림 구성 차이 감지: area={total_diff_area_ratio}, roi_count={diff_roi_count}"
        )

    # 2. 카드 UI 화면: 중앙 그림/카드 구성이 크게 다르면 FAIL
    elif (
        category == "card_ui" and total_diff_area_ratio >= 0.10 and diff_roi_count >= 8
    ):
        final_status = "FAIL"
        final_reasons.append(
            f"카드 UI 화면에서 큰 구조 차이 감지: area={total_diff_area_ratio}, roi_count={diff_roi_count}"
        )

    # 3. 텍스트 목록 화면: 넓은 영역 차이 또는 여러 FAIL ROI는 명확한 구성 차이로 판단
    elif category == "text_list" and (
        (total_diff_area_ratio >= 0.07 and diff_roi_count >= 8) or fail_count >= 3
    ):
        final_status = "FAIL"
        final_reasons.append(
            f"텍스트 목록 화면에서 큰 누락/구성 차이 감지: area={total_diff_area_ratio}, roi_count={diff_roi_count}, fail_roi={fail_count}"
        )

    # 4. 상태/시간 화면:
    # status_time은 숫자, 게이지, 위치 차이 때문에 OCR 누락 오탐이 자주 발생한다.
    # 따라서 missing_text_count만으로는 FAIL 확정하지 않고 REVIEW로 보낸다.
    # 상태/시간 화면에서 중요한 텍스트가 명확히 누락된 경우
    elif category == "status_time" and confirmed_missing_text_count >= 1:
        final_status = "FAIL"
        final_reasons.append(
            "기준 화면의 고신뢰도 텍스트가 " "검사 화면에서 명확하게 누락됨"
        )
    elif (
        category == "status_time"
        and missing_text_count >= 1
        and total_diff_area_ratio >= 0.045
        and diff_roi_count >= 5
    ):
        final_status = "REVIEW"
        final_reasons.append(
            f"상태/시간 화면에서 텍스트 누락 후보가 있으나 OCR/게이지/위치 차이 가능성으로 REVIEW 처리: missing_text_count={missing_text_count}, area={total_diff_area_ratio}, roi_count={diff_roi_count}"
        )

    # 5. 설정 화면: 작은 영역이라도 기준 텍스트가 사라진 경우는 FAIL
    elif (
        category == "setting_control"
        and missing_text_count >= 1
        and total_diff_area_ratio <= 0.012
        and diff_roi_count <= 3
    ):
        final_status = "FAIL"
        final_reasons.append(
            f"설정 화면에서 기준 텍스트 누락 가능성 감지: missing_text_count={missing_text_count}, area={total_diff_area_ratio}"
        )

    elif total_diff_area_ratio >= fail_area_ratio and not loading_like:
        severe_area_ratio = max(0.12, fail_area_ratio * 1.8)

        if total_diff_area_ratio >= severe_area_ratio:
            if category == "popup":
                final_status = "REVIEW"
                final_reasons.append(
                    f"팝업 화면에서 전체 차이 면적은 크지만 화면 색/게이지/위치 차이 가능성이 있어 REVIEW 처리: {total_diff_area_ratio} >= {severe_area_ratio}"
                )
            else:
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
        # text_list / status_time / setting_control은 OCR 또는 SSIM 오탐으로
        # 여러 개의 작은 ROI가 생길 수 있다.
        # 따라서 큰 구조 변화가 아니라면 바로 FAIL로 확정하지 않고 REVIEW로 보낸다.
        if category in {"text_list", "status_time", "setting_control"}:
            if fail_count <= 2 and total_diff_area_ratio <= 0.07:
                final_status = "REVIEW"
                final_reasons.append(
                    f"FAIL ROI {fail_count}개가 있으나 텍스트/설정/상태 화면의 OCR·SSIM 오탐 가능성으로 REVIEW 처리"
                )
            else:
                final_status = "FAIL"
                final_reasons.append(f"FAIL ROI {fail_count}개 존재")

        else:
            final_status = "FAIL"
            final_reasons.append(f"FAIL ROI {fail_count}개 존재")

    elif review_count > 0:
        auto_pass, auto_pass_reason = can_auto_pass_review_item(
            category=category,
            total_diff_area_ratio=total_diff_area_ratio,
            diff_roi_count=diff_roi_count,
            fail_count=fail_count,
            review_count=review_count,
            loading_like=loading_like,
        )

        if auto_pass:
            final_status = "PASS"
            final_reasons.append(auto_pass_reason)
        else:
            final_status = "REVIEW"
            final_reasons.append(f"REVIEW ROI {review_count}개 존재")
            final_reasons.append(auto_pass_reason)

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
            "confirmed_missing_text_count": confirmed_missing_text_count,
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
        "confirmed_missing_text_count",
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
                    "confirmed_missing_text_count": item["roi_decision_summary"][
                        "confirmed_missing_text_count"
                    ],
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
