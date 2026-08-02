import csv
import json
import re
import unicodedata
from pathlib import Path

import cv2
import numpy as np

try:
    from modules.path_config import (
        PROJECT_ROOT,
        RESULTS_DIR,
        DETECTED_ROIS_PATH,
        INSPECTION_RESULTS_PATH,
        INSPECTION_PROFILES_PATH,
        REFERENCE_REGISTRY_PATH,
    )
except ModuleNotFoundError:
    from path_config import (
        PROJECT_ROOT,
        RESULTS_DIR,
        DETECTED_ROIS_PATH,
        INSPECTION_RESULTS_PATH,
        INSPECTION_PROFILES_PATH,
        REFERENCE_REGISTRY_PATH,
    )


SSIM_RESULTS_PATH = RESULTS_DIR / "ssim_results.json"
OCR_RESULTS_PATH = RESULTS_DIR / "ocr_results.json"
INSPECTION_SUMMARY_CSV_PATH = RESULTS_DIR / "inspection_summary.csv"


def load_json(path: Path, name: str):
    if not path.exists():
        raise FileNotFoundError(f"{name} 파일이 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_registry():
    if not REFERENCE_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"reference_registry.csv 파일이 없습니다: {REFERENCE_REGISTRY_PATH}"
        )

    registry = {}

    with open(REFERENCE_REGISTRY_PATH, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            file_name = row.get("file_name", "").strip()
            if file_name:
                registry[file_name] = row

    return registry


def read_image(relative_path: str, flags=cv2.IMREAD_COLOR):
    image_path = PROJECT_ROOT / relative_path

    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {image_path}")

    data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(data, flags)

    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

    return image


def expected_to_binary(expected_result: str, binary_policy: dict):
    """
    expected_result는 임계값 검증과 결과 분석에만 사용한다.
    실제 PASS/FAIL 판정 로직에서는 절대 참조하지 않는다.
    """
    expected = (expected_result or "").strip().upper()

    if expected == "PASS":
        return "PASS"
    if expected == "FAIL":
        return "FAIL"
    if expected == "REVIEW":
        return binary_policy.get("expected_review_mapping", "FAIL")
    return "UNKNOWN"


def is_check_enabled(binary_policy: dict, check_name: str) -> bool:
    """Return whether an optional inspection check is enabled."""
    enabled_checks = binary_policy.get("enabled_checks", {})
    return bool(enabled_checks.get(check_name, True))


def is_cjk_ideograph(char: str) -> bool:
    if not char:
        return False

    codepoint = ord(char)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def normalize_spacing_for_judgement(text: str) -> str:
    """
    Preserve meaningful spaces while suppressing OCR-only CJK word splitting.

    Tesseract often inserts arbitrary spaces between Chinese ideographs. Those
    spaces are not treated as UI spacing. Spaces in Korean or Latin text remain
    intact, so a change such as "아버지 가방" -> "아버지가 방" is detectable.
    """
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        return ""

    chars = list(normalized)
    result = []

    for index, char in enumerate(chars):
        if char != " ":
            result.append(char)
            continue

        previous_char = next(
            (
                chars[position]
                for position in range(index - 1, -1, -1)
                if chars[position] != " "
            ),
            "",
        )
        next_char = next(
            (
                chars[position]
                for position in range(index + 1, len(chars))
                if chars[position] != " "
            ),
            "",
        )

        if is_cjk_ideograph(previous_char) and is_cjk_ideograph(next_char):
            continue
        result.append(" ")

    return "".join(result).strip()


def is_spacing_sensitive_text(text: str) -> bool:
    """Limit strict spacing checks to scripts where OCR spaces are meaningful."""
    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or "")))
    if not compact:
        return False

    hangul_count = sum(1 for char in compact if 0xAC00 <= ord(char) <= 0xD7A3)
    if hangul_count >= 2:
        return True

    semantic_chars = [char for char in compact if char.isalnum()]
    ascii_alnum_count = sum(
        1 for char in semantic_chars if char.isascii() and char.isalnum()
    )
    return (
        ascii_alnum_count >= 3
        and ascii_alnum_count / max(len(semantic_chars), 1) >= 0.80
    )


def has_spacing_mismatch(ocr_roi: dict) -> bool:
    if not ocr_roi:
        return False

    reference_text = ocr_roi.get("reference_ocr", {}).get("text", "")
    capture_text = ocr_roi.get("capture_ocr", {}).get("text", "")
    reference_normalized = normalize_spacing_for_judgement(reference_text)
    capture_normalized = normalize_spacing_for_judgement(capture_text)

    if not reference_normalized or not capture_normalized:
        return False
    if not (
        is_spacing_sensitive_text(reference_normalized)
        and is_spacing_sensitive_text(capture_normalized)
    ):
        return False

    reference_compact = re.sub(r"\s+", "", reference_normalized)
    capture_compact = re.sub(r"\s+", "", capture_normalized)

    return (
        reference_compact == capture_compact
        and reference_normalized != capture_normalized
    )


def normalize_text_for_judgement(text: str) -> str:
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
    for char in remove_chars:
        normalized = normalized.replace(char, "")
    return normalized.strip()


def get_ocr_min_confidence(ocr_roi: dict) -> float:
    if not ocr_roi:
        return 0.0

    reference_confidence = float(
        ocr_roi.get("reference_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )
    capture_confidence = float(
        ocr_roi.get("capture_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )
    return min(reference_confidence, capture_confidence)


def has_number_mismatch(ocr_compare: dict) -> bool:
    reference_numbers = ocr_compare.get("reference_numbers", [])
    capture_numbers = ocr_compare.get("capture_numbers", [])

    if not reference_numbers and not capture_numbers:
        return False

    return reference_numbers != capture_numbers


def has_text_mismatch(ocr_compare: dict) -> bool:
    reference_text = normalize_text_for_judgement(
        ocr_compare.get("reference_text_compact", "")
    )
    capture_text = normalize_text_for_judgement(
        ocr_compare.get("capture_text_compact", "")
    )

    if not reference_text or not capture_text:
        return False

    return reference_text != capture_text


def has_confirmed_missing_text(ocr_roi: dict, ssim_roi: dict, rules: dict) -> bool:
    if not ocr_roi or not ssim_roi:
        return False

    ocr_compare = ocr_roi.get("ocr_compare", {})
    reference_text = normalize_text_for_judgement(
        ocr_compare.get("reference_text_compact", "")
    )
    reference_confidence = float(
        ocr_roi.get("reference_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )
    capture_confidence = float(
        ocr_roi.get("capture_ocr", {}).get("mean_confidence", 0.0) or 0.0
    )
    area_ratio = float(ocr_roi.get("area_ratio", 0.0) or 0.0)

    return (
        len(reference_text) >= int(rules.get("min_reference_text_length", 4))
        and reference_confidence
        >= float(rules.get("min_reference_confidence", 0.80))
        and capture_confidence <= float(rules.get("max_capture_confidence", 0.40))
        and ssim_roi.get("ssim_status") == "FAIL"
        and area_ratio >= float(rules.get("min_area_ratio", 0.01))
    )


def build_roi_evidence(
    category: str,
    diff_roi: dict,
    ssim_roi: dict,
    ocr_roi: dict,
    binary_policy: dict,
):
    roi_id = diff_roi.get("roi_id", "")
    ocr_compare = ocr_roi.get("ocr_compare", {}) if ocr_roi else {}
    ocr_min_confidence = get_ocr_min_confidence(ocr_roi)
    number_mismatch = has_number_mismatch(ocr_compare)
    text_mismatch = has_text_mismatch(ocr_compare)
    spacing_mismatch = has_spacing_mismatch(ocr_roi)
    confirmed_missing = has_confirmed_missing_text(
        ocr_roi,
        ssim_roi,
        binary_policy.get("confirmed_missing_text", {}),
    )

    strong_fail_reasons = []

    if confirmed_missing and is_check_enabled(binary_policy, "text_content"):
        strong_fail_reasons.append("기준의 중요 텍스트가 Capture에서 누락 또는 교체됨")

    spacing_rules = binary_policy.get("text_spacing", {})
    if (
        is_check_enabled(binary_policy, "text_spacing")
        and spacing_mismatch
        and ocr_min_confidence
        >= float(spacing_rules.get("min_ocr_confidence", 0.80))
    ):
        strong_fail_reasons.append(
            "글자 내용은 같지만 의미 있는 띄어쓰기가 다름"
        )

    setting_rules = binary_policy.get("setting_control", {})
    if (
        is_check_enabled(binary_policy, "text_content")
        and category == "setting_control"
        and number_mismatch
        and ocr_min_confidence
        >= float(setting_rules.get("numeric_confidence", 0.70))
    ):
        strong_fail_reasons.append("설정값 숫자 불일치")

    roi_status = "FAIL" if strong_fail_reasons else "PASS"

    return {
        "roi_id": roi_id,
        "roi_final_status": roi_status,
        "roi_reason": strong_fail_reasons
        or ["화면 전체 규칙에서 사용할 차이 증거로 기록"],
        "area_ratio": float(diff_roi.get("area_ratio", 0.0) or 0.0),
        "ssim_score": ssim_roi.get("ssim_score") if ssim_roi else None,
        "ssim_status": ssim_roi.get("ssim_status", "MISSING")
        if ssim_roi
        else "MISSING",
        "ocr_status": ocr_compare.get("ocr_compare_status", "MISSING"),
        "ocr_min_confidence": ocr_min_confidence,
        "number_mismatch": number_mismatch,
        "text_mismatch": text_mismatch,
        "spacing_mismatch": spacing_mismatch,
        "confirmed_missing_text": confirmed_missing,
    }


def has_card_localized_missing(ocr_rois: dict, rules: dict) -> bool:
    min_reference_confidence = float(
        rules.get("localized_missing_min_reference_confidence", 0.75)
    )
    max_capture_confidence = float(
        rules.get("localized_missing_max_capture_confidence", 0.20)
    )
    min_area_ratio = float(rules.get("localized_missing_min_area_ratio", 0.001))

    for ocr_roi in ocr_rois.values():
        ocr_compare = ocr_roi.get("ocr_compare", {})
        reference_text = normalize_text_for_judgement(
            ocr_compare.get("reference_text_compact", "")
        )
        capture_text = normalize_text_for_judgement(
            ocr_compare.get("capture_text_compact", "")
        )
        reference_confidence = float(
            ocr_roi.get("reference_ocr", {}).get("mean_confidence", 0.0) or 0.0
        )
        capture_confidence = float(
            ocr_roi.get("capture_ocr", {}).get("mean_confidence", 0.0) or 0.0
        )
        area_ratio = float(ocr_roi.get("area_ratio", 0.0) or 0.0)

        if (
            reference_text
            and not capture_text
            and reference_confidence >= min_reference_confidence
            and capture_confidence <= max_capture_confidence
            and area_ratio >= min_area_ratio
        ):
            return True

    return False


def count_high_confidence_text_mismatches(ocr_rois: dict, threshold: float) -> int:
    count = 0

    for ocr_roi in ocr_rois.values():
        ocr_compare = ocr_roi.get("ocr_compare", {})
        if has_text_mismatch(ocr_compare) and get_ocr_min_confidence(ocr_roi) >= threshold:
            count += 1

    return count


def count_high_confidence_spacing_mismatches(
    ocr_rois: dict,
    threshold: float,
) -> int:
    return sum(
        1
        for ocr_roi in ocr_rois.values()
        if has_spacing_mismatch(ocr_roi)
        and get_ocr_min_confidence(ocr_roi) >= threshold
    )


def get_min_ssim(ssim_rois: dict) -> float:
    scores = [
        float(roi.get("ssim_score"))
        for roi in ssim_rois.values()
        if roi.get("ssim_score") is not None
    ]
    return min(scores) if scores else 1.0


def compute_matched_text_brightness_loss(
    reference_image,
    capture_image,
    diff_rois: list,
    ocr_rois: dict,
):
    """
    OCR 내용은 같지만 Capture 글자가 흐려졌는지 확인한다.
    각 OCR PASS ROI의 밝은 픽셀 90백분위 값을 비교한다.
    양수 값이 클수록 Capture 글자가 Reference보다 어둡다.
    """
    reference_gray = cv2.cvtColor(reference_image, cv2.COLOR_BGR2GRAY)
    capture_gray = cv2.cvtColor(capture_image, cv2.COLOR_BGR2GRAY)
    losses = []

    for diff_roi in diff_rois:
        roi_id = diff_roi.get("roi_id")
        ocr_roi = ocr_rois.get(roi_id, {})
        ocr_status = ocr_roi.get("ocr_compare", {}).get("ocr_compare_status")

        if ocr_status != "PASS":
            continue

        x, y, width, height = diff_roi.get("bbox", [0, 0, 0, 0])
        reference_crop = reference_gray[y : y + height, x : x + width]
        capture_crop = capture_gray[y : y + height, x : x + width]

        if reference_crop.size == 0 or capture_crop.size == 0:
            continue

        reference_bright = float(np.percentile(reference_crop, 90))
        capture_bright = float(np.percentile(capture_crop, 90))
        losses.append(reference_bright - capture_bright)

    mean_loss = float(np.mean(losses)) if losses else 0.0

    return {
        "matched_roi_count": len(losses),
        "mean_brightness_loss": round(mean_loss, 4),
    }


def compute_localized_brightness_loss(reference_image, capture_image, diff_rois: list):
    """
    Measure how much a small changed label became dimmer.

    Brightness is compared instead of glyph shape, so a font-family change by
    itself is not a failure. This is used for localized setting values such as
    a faded temperature label.
    """
    reference_gray = cv2.cvtColor(reference_image, cv2.COLOR_BGR2GRAY)
    capture_gray = cv2.cvtColor(capture_image, cv2.COLOR_BGR2GRAY)
    losses = []

    for diff_roi in diff_rois:
        x, y, width, height = diff_roi.get("bbox", [0, 0, 0, 0])
        reference_crop = reference_gray[y : y + height, x : x + width]
        capture_crop = capture_gray[y : y + height, x : x + width]

        if reference_crop.size == 0 or capture_crop.size == 0:
            continue

        reference_bright = float(np.percentile(reference_crop, 90))
        capture_bright = float(np.percentile(capture_crop, 90))
        losses.append(reference_bright - capture_bright)

    return {
        "roi_count": len(losses),
        "max_brightness_loss": round(max(losses, default=0.0), 4),
    }


def find_progress_bar_fill(image, rules: dict):
    """
    상태 화면에서 채도가 높은 가로 막대의 채워진 길이를 찾는다.
    반환 비율은 전체 이미지 너비 대비 막대 너비이다.
    """
    image_height, image_width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_min = int(rules.get("progress_bar_saturation_min", 120))
    value_min = int(rules.get("progress_bar_value_min", 100))
    min_width_ratio = float(rules.get("progress_bar_min_width_ratio", 0.06))
    max_height = int(rules.get("progress_bar_max_height", 60))
    min_aspect_ratio = float(rules.get("progress_bar_min_aspect_ratio", 4.0))
    min_y_ratio = float(rules.get("progress_bar_min_y_ratio", 0.45))

    mask = (
        (hsv[:, :, 1] >= saturation_min) & (hsv[:, :, 2] >= value_min)
    ).astype(np.uint8) * 255
    close_kernel = np.ones((5, 15), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []

    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        width_ratio = width / image_width
        aspect_ratio = width / max(height, 1)

        if (
            width_ratio >= min_width_ratio
            and height <= max_height
            and aspect_ratio >= min_aspect_ratio
            and y / image_height >= min_y_ratio
        ):
            candidates.append(
                {
                    "bbox": [int(x), int(y), int(width), int(height)],
                    "fill_width_ratio": round(float(width_ratio), 6),
                }
            )

    if not candidates:
        return {"found": False, "fill_width_ratio": None, "bbox": None}

    best = max(candidates, key=lambda item: item["fill_width_ratio"])
    return {"found": True, **best}


def compare_progress_bar(reference_image, capture_image, rules: dict):
    reference_bar = find_progress_bar_fill(reference_image, rules)
    capture_bar = find_progress_bar_fill(capture_image, rules)

    if reference_bar["found"] and capture_bar["found"]:
        delta = abs(
            reference_bar["fill_width_ratio"] - capture_bar["fill_width_ratio"]
        )
    else:
        delta = None

    return {
        "reference": reference_bar,
        "capture": capture_bar,
        "fill_delta": round(float(delta), 6) if delta is not None else None,
    }


def compute_gradient_color_difference(reference_image, capture_image, rules: dict):
    """
    Compare smooth colored surfaces without comparing their exact positions.

    A moving, textured picture can change position without failing when its color
    distribution stays similar. A UI gradient that loses or changes color makes
    the smooth-color area or HSV histogram change significantly.
    """
    saturation_min = int(rules.get("saturation_min", 40))
    value_min = int(rules.get("value_min", 25))
    value_max = int(rules.get("value_max", 245))
    smooth_edge_max = float(rules.get("smooth_edge_max", 10.0))
    hue_bins = int(rules.get("hue_bins", 18))
    saturation_bins = int(rules.get("saturation_bins", 16))

    features = []

    for image in (reference_image, capture_image):
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        edge_magnitude = cv2.magnitude(gradient_x, gradient_y)

        smooth_color_mask = (
            (hsv[:, :, 1] >= saturation_min)
            & (hsv[:, :, 2] >= value_min)
            & (hsv[:, :, 2] <= value_max)
            & (edge_magnitude <= smooth_edge_max)
        )
        mask = smooth_color_mask.astype(np.uint8)
        area_ratio = float(np.mean(smooth_color_mask))

        histogram = cv2.calcHist(
            [hsv],
            [0, 1],
            mask,
            [hue_bins, saturation_bins],
            [0, 180, 0, 256],
        )
        if np.any(mask):
            histogram = cv2.normalize(
                histogram,
                None,
                alpha=1,
                beta=0,
                norm_type=cv2.NORM_L1,
            )

        features.append({"area_ratio": area_ratio, "histogram": histogram})

    reference_feature, capture_feature = features
    if reference_feature["area_ratio"] > 0 and capture_feature["area_ratio"] > 0:
        histogram_distance = float(
            cv2.compareHist(
                reference_feature["histogram"],
                capture_feature["histogram"],
                cv2.HISTCMP_BHATTACHARYYA,
            )
        )
    else:
        histogram_distance = 0.0

    area_delta = abs(
        reference_feature["area_ratio"] - capture_feature["area_ratio"]
    )
    max_area_ratio = max(
        reference_feature["area_ratio"], capture_feature["area_ratio"]
    )

    return {
        "reference_smooth_color_area_ratio": round(
            reference_feature["area_ratio"], 6
        ),
        "capture_smooth_color_area_ratio": round(
            capture_feature["area_ratio"], 6
        ),
        "smooth_color_area_delta": round(area_delta, 6),
        "color_histogram_distance": round(histogram_distance, 6),
        "max_smooth_color_area_ratio": round(max_area_ratio, 6),
    }


def is_gradient_color_failure(evidence: dict, rules: dict) -> bool:
    max_area_ratio = float(evidence.get("max_smooth_color_area_ratio", 0.0))
    area_delta = float(evidence.get("smooth_color_area_delta", 0.0))
    histogram_distance = float(evidence.get("color_histogram_distance", 0.0))

    return (
        max_area_ratio
        >= float(rules.get("min_smooth_color_area_ratio", 0.03))
        and (
            area_delta
            >= float(rules.get("smooth_color_area_delta_fail", 0.025))
            or histogram_distance
            >= float(rules.get("color_histogram_distance_fail", 0.65))
        )
    )


def decide_one_item(
    file_name: str,
    diff_item: dict,
    ssim_item: dict,
    ocr_item: dict,
    registry_row: dict,
    binary_policy: dict,
):
    screen_id = diff_item.get("screen_id", Path(file_name).stem)
    category = diff_item.get("category", registry_row.get("category", "general_diff"))
    profile_name = diff_item.get(
        "profile", registry_row.get("profile", "general_diff_profile")
    )
    expected_result = registry_row.get("expected_result", "UNKNOWN")

    diff_rois = diff_item.get("rois", [])
    ssim_rois = {
        roi.get("roi_id"): roi for roi in (ssim_item or {}).get("roi_results", [])
    }
    ocr_rois = {
        roi.get("roi_id"): roi for roi in (ocr_item or {}).get("roi_results", [])
    }

    diff_roi_count = int(diff_item.get("diff_roi_count", len(diff_rois)))
    total_diff_area_ratio = float(
        diff_item.get("total_diff_area_ratio", 0.0) or 0.0
    )
    overall_ssim = (ssim_item or {}).get("overall_ssim")

    roi_decisions = []
    for diff_roi in diff_rois:
        roi_id = diff_roi.get("roi_id")
        roi_decisions.append(
            build_roi_evidence(
                category=category,
                diff_roi=diff_roi,
                ssim_roi=ssim_rois.get(roi_id, {}),
                ocr_roi=ocr_rois.get(roi_id, {}),
                binary_policy=binary_policy,
            )
        )

    roi_fail_count = sum(
        1 for item in roi_decisions if item["roi_final_status"] == "FAIL"
    )
    roi_pass_count = len(roi_decisions) - roi_fail_count
    confirmed_missing_count = sum(
        1 for item in roi_decisions if item["confirmed_missing_text"]
    )

    text_rules = binary_policy.get("text_list", {})
    high_confidence_text_mismatch_count = count_high_confidence_text_mismatches(
        ocr_rois,
        float(text_rules.get("text_confidence", 0.70)),
    )
    spacing_rules = binary_policy.get("text_spacing", {})
    high_confidence_spacing_mismatch_count = (
        count_high_confidence_spacing_mismatches(
            ocr_rois,
            float(spacing_rules.get("min_ocr_confidence", 0.80)),
        )
    )
    min_ssim = get_min_ssim(ssim_rois)

    reference_image = None
    capture_image = None
    brightness_evidence = {
        "matched_roi_count": 0,
        "mean_brightness_loss": 0.0,
    }
    localized_brightness_evidence = {
        "roi_count": 0,
        "max_brightness_loss": 0.0,
    }
    progress_bar_evidence = {
        "reference": {"found": False, "fill_width_ratio": None, "bbox": None},
        "capture": {"found": False, "fill_width_ratio": None, "bbox": None},
        "fill_delta": None,
    }
    gradient_color_evidence = {
        "reference_smooth_color_area_ratio": 0.0,
        "capture_smooth_color_area_ratio": 0.0,
        "smooth_color_area_delta": 0.0,
        "color_histogram_distance": 0.0,
        "max_smooth_color_area_ratio": 0.0,
    }

    if diff_roi_count > 0 and category in {
        "text_list",
        "status_time",
        "card_ui",
        "popup",
        "setting_control",
    }:
        reference_image = read_image(diff_item.get("reference_image", ""))
        capture_image = read_image(diff_item.get("capture_image", ""))

    if category == "text_list" and reference_image is not None:
        brightness_evidence = compute_matched_text_brightness_loss(
            reference_image,
            capture_image,
            diff_rois,
            ocr_rois,
        )

    if category == "setting_control" and reference_image is not None:
        localized_brightness_evidence = compute_localized_brightness_loss(
            reference_image,
            capture_image,
            diff_rois,
        )

    if category == "status_time" and reference_image is not None:
        progress_bar_evidence = compare_progress_bar(
            reference_image,
            capture_image,
            binary_policy.get("status_time", {}),
        )

    if category in {"card_ui", "popup"} and reference_image is not None:
        gradient_color_evidence = compute_gradient_color_difference(
            reference_image,
            capture_image,
            binary_policy.get("gradient_color", {}),
        )

    final_status = "PASS"
    final_reasons = []
    applied_rule = "within_tolerance"

    if diff_roi_count == 0:
        final_reasons.append("차이 ROI가 검출되지 않음")
        applied_rule = "no_difference"

    elif (
        is_check_enabled(binary_policy, "text_content")
        and confirmed_missing_count >= 1
    ):
        final_status = "FAIL"
        final_reasons.append(
            f"중요 텍스트 누락 또는 교체 증거 {confirmed_missing_count}개"
        )
        applied_rule = "confirmed_missing_text"

    elif (
        is_check_enabled(binary_policy, "text_spacing")
        and high_confidence_spacing_mismatch_count >= 1
    ):
        final_status = "FAIL"
        final_reasons.append(
            "글자 내용은 같지만 의미 있는 띄어쓰기가 다름: "
            f"count={high_confidence_spacing_mismatch_count}"
        )
        applied_rule = "text_spacing_difference"

    elif category == "guide_image":
        rules = binary_policy.get("guide_image", {})
        if (
            is_check_enabled(binary_policy, "image_structure")
            and total_diff_area_ratio
            >= float(rules.get("fail_area_ratio", 0.085))
            and diff_roi_count >= int(rules.get("min_diff_roi_count", 4))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "안내 그림의 넓은 영역에서 구조 차이가 검출됨: "
                f"area={total_diff_area_ratio}, roi_count={diff_roi_count}"
            )
            applied_rule = "guide_image_large_difference"

    elif category == "card_ui":
        rules = binary_policy.get("card_ui", {})
        gradient_rules = binary_policy.get("gradient_color", {})
        gradient_failure = is_gradient_color_failure(
            gradient_color_evidence,
            gradient_rules,
        )
        if (
            is_check_enabled(binary_policy, "gradient_color")
            and gradient_failure
        ):
            final_status = "FAIL"
            final_reasons.append(
                "카드 UI의 부드러운 그라데이션 영역에서 색 분포 차이가 검출됨: "
                f"area_delta={gradient_color_evidence['smooth_color_area_delta']}, "
                f"histogram_distance={gradient_color_evidence['color_histogram_distance']}"
            )
            applied_rule = "card_ui_gradient_color_difference"
        elif (
            is_check_enabled(binary_policy, "image_structure")
            and not gradient_failure
            and total_diff_area_ratio
            >= float(rules.get("major_structure_fail_area_ratio", 0.10))
            and diff_roi_count
            >= int(rules.get("major_structure_min_diff_roi_count", 5))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "카드 UI의 여러 구성 요소가 동시에 큰 폭으로 달라짐: "
                f"area={total_diff_area_ratio}, roi_count={diff_roi_count}"
            )
            applied_rule = "card_ui_major_structure_difference"
        elif (
            is_check_enabled(binary_policy, "text_content")
            and not gradient_failure
            and has_card_localized_missing(ocr_rois, rules)
        ):
            final_status = "FAIL"
            final_reasons.append("카드 UI에서 국소 텍스트 누락이 검출됨")
            applied_rule = "card_ui_localized_missing_text"

    elif category == "popup":
        rules = binary_policy.get("popup", {})
        gradient_rules = binary_policy.get("gradient_color", {})
        gradient_failure = is_gradient_color_failure(
            gradient_color_evidence,
            gradient_rules,
        )
        if (
            is_check_enabled(binary_policy, "gradient_color")
            and gradient_failure
        ):
            final_status = "FAIL"
            final_reasons.append(
                "팝업의 보라색 그라데이션 영역에서 색 분포 차이가 검출됨: "
                f"area_delta={gradient_color_evidence['smooth_color_area_delta']}, "
                f"histogram_distance={gradient_color_evidence['color_histogram_distance']}"
            )
            applied_rule = "popup_gradient_color_difference"
        elif (
            is_check_enabled(binary_policy, "image_structure")
            and not gradient_failure
            and total_diff_area_ratio
            >= float(rules.get("major_structure_fail_area_ratio", 0.10))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "팝업의 전체 구조와 배치 차이가 허용 범위를 초과함: "
                f"area={total_diff_area_ratio}"
            )
            applied_rule = "popup_major_structure_difference"

    elif category == "setting_control":
        rules = binary_policy.get("setting_control", {})
        localized_brightness_loss = float(
            localized_brightness_evidence["max_brightness_loss"]
        )
        if roi_fail_count >= 1:
            final_status = "FAIL"
            final_reasons.append("설정값 숫자 또는 중요 텍스트 오류가 검출됨")
            applied_rule = "setting_semantic_difference"
        elif (
            is_check_enabled(binary_policy, "text_brightness")
            and diff_roi_count <= int(rules.get("localized_max_roi_count", 2))
            and localized_brightness_loss
            >= float(rules.get("localized_brightness_loss_fail", 80.0))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "설정 화면의 국소 글자 밝기가 크게 감소함: "
                f"roi_count={diff_roi_count}, brightness_loss={localized_brightness_loss}"
            )
            applied_rule = "setting_text_brightness_loss"

    elif category == "status_time":
        rules = binary_policy.get("status_time", {})
        fill_delta = progress_bar_evidence.get("fill_delta")
        if (
            is_check_enabled(binary_policy, "progress_bar")
            and fill_delta is not None
            and fill_delta
            >= float(rules.get("progress_bar_fill_delta_fail", 0.025))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "진행 상태 바의 채워진 길이 차이가 허용 기준을 초과함: "
                f"delta={fill_delta}"
            )
            applied_rule = "status_progress_bar_difference"

    elif category == "text_list":
        rules = binary_policy.get("text_list", {})
        brightness_loss = float(brightness_evidence["mean_brightness_loss"])

        if (
            is_check_enabled(binary_policy, "image_structure")
            and total_diff_area_ratio
            >= float(rules.get("large_diff_area_ratio", 0.07))
            and diff_roi_count >= int(rules.get("large_diff_min_roi_count", 8))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "텍스트 목록의 넓은 영역에서 누락 또는 구조 차이가 검출됨"
            )
            applied_rule = "text_list_large_difference"
        elif (
            is_check_enabled(binary_policy, "text_content")
            and high_confidence_text_mismatch_count
            >= int(rules.get("high_confidence_text_mismatch_count", 3))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "신뢰도 높은 텍스트 불일치가 여러 ROI에서 검출됨: "
                f"count={high_confidence_text_mismatch_count}"
            )
            applied_rule = "text_list_multiple_text_mismatches"
        elif (
            is_check_enabled(binary_policy, "text_brightness")
            and brightness_loss
            >= float(rules.get("matched_text_brightness_loss_fail", 40.0))
        ):
            final_status = "FAIL"
            final_reasons.append(
                "내용은 같지만 Capture 텍스트 밝기·대비가 크게 감소함: "
                f"brightness_loss={brightness_loss}"
            )
            applied_rule = "text_list_brightness_loss"

    elif (
        is_check_enabled(binary_policy, "image_structure")
        and total_diff_area_ratio
        >= float(binary_policy.get("general_fail_area_ratio", 0.12))
    ):
        final_status = "FAIL"
        final_reasons.append(
            "전체 차이 면적이 일반 화면 허용 기준을 초과함: "
            f"{total_diff_area_ratio}"
        )
        applied_rule = "general_large_difference"

    if not final_reasons:
        final_reasons.append("선택된 카테고리의 PASS 허용 임계값 이내")

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": category,
        "profile": profile_name,
        "reference_image": diff_item.get("reference_image", ""),
        "capture_image": diff_item.get("capture_image", ""),
        "expected_result": expected_result,
        "expected_binary_result": expected_to_binary(expected_result, binary_policy),
        "memo": registry_row.get("memo", ""),
        "final_status": final_status,
        "applied_rule": applied_rule,
        "final_reasons": final_reasons,
        "diff_summary": {
            "diff_roi_count": diff_roi_count,
            "total_diff_area_ratio": total_diff_area_ratio,
        },
        "evidence_summary": {
            "overall_ssim": overall_ssim,
            "minimum_roi_ssim": round(float(min_ssim), 6),
            "confirmed_missing_text_count": confirmed_missing_count,
            "high_confidence_text_mismatch_count": high_confidence_text_mismatch_count,
            "high_confidence_spacing_mismatch_count": high_confidence_spacing_mismatch_count,
            "matched_text_brightness": brightness_evidence,
            "localized_text_brightness": localized_brightness_evidence,
            "progress_bar": progress_bar_evidence,
            "gradient_color": gradient_color_evidence,
        },
        "roi_decision_summary": {
            "pass_count": roi_pass_count,
            "fail_count": roi_fail_count,
        },
        "roi_decisions": roi_decisions,
        "debug_images": {"diff_debug": diff_item.get("debug_image", "")},
    }


def save_summary_csv(results: dict):
    fieldnames = [
        "screen_id",
        "file_name",
        "category",
        "profile",
        "expected_result",
        "expected_binary_result",
        "final_status",
        "applied_rule",
        "diff_roi_count",
        "pass_roi_count",
        "fail_roi_count",
        "total_diff_area_ratio",
        "overall_ssim",
        "minimum_roi_ssim",
        "confirmed_missing_text_count",
        "high_confidence_text_mismatch_count",
        "high_confidence_spacing_mismatch_count",
        "matched_text_brightness_loss",
        "localized_text_brightness_loss",
        "progress_bar_fill_delta",
        "gradient_smooth_color_area_delta",
        "gradient_color_histogram_distance",
        "memo",
        "final_reasons",
    ]

    with open(INSPECTION_SUMMARY_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for item in results.values():
            evidence = item["evidence_summary"]
            writer.writerow(
                {
                    "screen_id": item["screen_id"],
                    "file_name": item["file_name"],
                    "category": item["category"],
                    "profile": item["profile"],
                    "expected_result": item["expected_result"],
                    "expected_binary_result": item["expected_binary_result"],
                    "final_status": item["final_status"],
                    "applied_rule": item["applied_rule"],
                    "diff_roi_count": item["diff_summary"]["diff_roi_count"],
                    "pass_roi_count": item["roi_decision_summary"]["pass_count"],
                    "fail_roi_count": item["roi_decision_summary"]["fail_count"],
                    "total_diff_area_ratio": item["diff_summary"][
                        "total_diff_area_ratio"
                    ],
                    "overall_ssim": evidence["overall_ssim"],
                    "minimum_roi_ssim": evidence["minimum_roi_ssim"],
                    "confirmed_missing_text_count": evidence[
                        "confirmed_missing_text_count"
                    ],
                    "high_confidence_text_mismatch_count": evidence[
                        "high_confidence_text_mismatch_count"
                    ],
                    "high_confidence_spacing_mismatch_count": evidence[
                        "high_confidence_spacing_mismatch_count"
                    ],
                    "matched_text_brightness_loss": evidence[
                        "matched_text_brightness"
                    ]["mean_brightness_loss"],
                    "localized_text_brightness_loss": evidence[
                        "localized_text_brightness"
                    ]["max_brightness_loss"],
                    "progress_bar_fill_delta": evidence["progress_bar"][
                        "fill_delta"
                    ],
                    "gradient_smooth_color_area_delta": evidence[
                        "gradient_color"
                    ]["smooth_color_area_delta"],
                    "gradient_color_histogram_distance": evidence[
                        "gradient_color"
                    ]["color_histogram_distance"],
                    "memo": item["memo"],
                    "final_reasons": " | ".join(item["final_reasons"]),
                }
            )


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
    binary_policy = inspection_profiles.get("binary_policy", {})

    results = {}
    errors = []

    for index, (file_name, diff_item) in enumerate(sorted(diff_items.items()), start=1):
        print(f"[{index:03d}/{len(diff_items)}] Binary deciding {file_name}")

        try:
            results[file_name] = decide_one_item(
                file_name=file_name,
                diff_item=diff_item,
                ssim_item=ssim_items.get(file_name, {}),
                ocr_item=ocr_items.get(file_name, {}),
                registry_row=registry.get(file_name, {}),
                binary_policy=binary_policy,
            )
        except Exception as error:
            errors.append({"file_name": file_name, "error": str(error)})
            print(f"  ERROR: {error}")

    pass_count = sum(1 for item in results.values() if item["final_status"] == "PASS")
    fail_count = sum(1 for item in results.values() if item["final_status"] == "FAIL")

    output = {
        "summary": {
            "total_items": len(diff_items),
            "processed_count": len(results),
            "error_count": len(errors),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "errors": errors,
        },
        "binary_policy": {
            "expected_review_mapping": binary_policy.get(
                "expected_review_mapping", "FAIL"
            ),
            "enabled_checks": binary_policy.get("enabled_checks", {}),
            "note": "expected_result는 판정에 사용하지 않고 사후 검증에만 사용함",
        },
        "results": results,
    }

    INSPECTION_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INSPECTION_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    save_summary_csv(results)
    return output


def print_summary(output: dict):
    summary = output["summary"]

    print("\n========== BINARY DECISION SUMMARY ==========")
    print(f"Total items : {summary['total_items']}")
    print(f"Processed   : {summary['processed_count']}")
    print(f"Errors      : {summary['error_count']}")
    print("---------------------------------------------")
    print(f"PASS count  : {summary['pass_count']}")
    print(f"FAIL count  : {summary['fail_count']}")
    print("---------------------------------------------")
    print(f"Saved JSON  : {INSPECTION_RESULTS_PATH}")
    print(f"Saved CSV   : {INSPECTION_SUMMARY_CSV_PATH}")
    print("=============================================")


def main():
    output = run_decision_engine()
    print_summary(output)


if __name__ == "__main__":
    main()
