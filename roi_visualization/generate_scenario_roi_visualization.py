from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


# =========================================================
# 0. 경로
# =========================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

RESULT_SCENARIOS_DIR = PROJECT_ROOT / "results" / "scenarios"
DATA_SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"

OUTPUT_ROOT = SCRIPT_DIR / "output"


# =========================================================
# 1. 시나리오
# =========================================================
SCENARIOS = {
    "model_a_round_1": "A-1차",
    "model_a_round_2": "A-2차",
    "model_a_round_3": "A-3차",
    "model_b": "B-1차",
}


# =========================================================
# 2. 표시 설정
# =========================================================
RED = (255, 0, 0)
BOX_PADDING = 8


# =========================================================
# 3. 기본 함수
# =========================================================
def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"JSON 구조 오류: {path}")

    return data


def normalize_status(value: Any) -> str:
    return str(value or "UNKNOWN").strip().upper()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_roi_id(item: dict[str, Any]) -> str:
    return str(
        item.get(
            "roi_id",
            item.get("id", ""),
        )
    ).strip()


def valid_bbox(bbox: Any) -> bool:
    return (
        isinstance(bbox, list)
        and len(bbox) == 4
    )


# =========================================================
# 4. ROI
# =========================================================
def get_detected_rois(
    detected_file_data: dict[str, Any],
) -> list[dict[str, Any]]:
    rois = detected_file_data.get(
        "rois",
        [],
    )

    if not isinstance(rois, list):
        return []

    return [
        roi
        for roi in rois
        if isinstance(roi, dict)
    ]


def build_bbox_map(
    detected_file_data: dict[str, Any],
) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}

    for roi in get_detected_rois(
        detected_file_data
    ):
        roi_id = get_roi_id(roi)
        bbox = roi.get("bbox")

        if (
            roi_id
            and valid_bbox(bbox)
        ):
            result[roi_id] = bbox

    return result


# =========================================================
# 5. 박스 그리기
# =========================================================
def draw_bbox(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    bbox: list[Any],
    padding: int = 0,
) -> bool:
    try:
        x, y, width, height = [
            int(round(float(value)))
            for value in bbox
        ]
    except (TypeError, ValueError):
        return False

    if width <= 0 or height <= 0:
        return False

    left = max(
        0,
        x - padding,
    )

    top = max(
        0,
        y - padding,
    )

    right = min(
        image.width - 1,
        x + width + padding,
    )

    bottom = min(
        image.height - 1,
        y + height + padding,
    )

    if right <= left or bottom <= top:
        return False

    line_width = max(
        3,
        round(
            min(image.size)
            * 0.004
        ),
    )

    draw.rectangle(
        [
            left,
            top,
            right,
            bottom,
        ],
        outline=RED,
        width=line_width,
    )

    return True


def draw_full_border(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
) -> None:
    line_width = max(
        5,
        round(
            min(image.size)
            * 0.007
        ),
    )

    draw.rectangle(
        [
            0,
            0,
            image.width - 1,
            image.height - 1,
        ],
        outline=RED,
        width=line_width,
    )


# =========================================================
# 6. 여러 bbox 합치기
# =========================================================
def merge_bboxes(
    bboxes: list[list[Any]],
) -> list[int] | None:
    normalized: list[
        tuple[int, int, int, int]
    ] = []

    for bbox in bboxes:
        if not valid_bbox(bbox):
            continue

        try:
            x, y, w, h = [
                int(round(float(value)))
                for value in bbox
            ]
        except (TypeError, ValueError):
            continue

        if w <= 0 or h <= 0:
            continue

        normalized.append(
            (
                x,
                y,
                x + w,
                y + h,
            )
        )

    if not normalized:
        return None

    left = min(
        item[0]
        for item in normalized
    )

    top = min(
        item[1]
        for item in normalized
    )

    right = max(
        item[2]
        for item in normalized
    )

    bottom = max(
        item[3]
        for item in normalized
    )

    return [
        left,
        top,
        right - left,
        bottom - top,
    ]


# =========================================================
# 7. 최종 오류 원인 문구
# =========================================================
def get_reason_text(
    selected_result: dict[str, Any],
) -> str:
    reasons = selected_result.get(
        "final_reasons",
        [],
    )

    if not isinstance(reasons, list):
        reasons = []

    return " ".join(
        str(reason)
        for reason in reasons
    ).lower()


# =========================================================
# 8. 상단 UI / 탭 오류
# =========================================================
def is_top_ui_error(
    selected_result: dict[str, Any],
) -> bool:
    rule = str(
        selected_result.get(
            "applied_rule",
            "",
        )
    ).lower()

    reason = get_reason_text(
        selected_result
    )

    reason_keywords = [
        "상단 ui",
        "상단ui",
        "상단 글자",
        "상단 탭",
        "탭 색상",
        "탭색상",
    ]

    rule_keywords = [
        "top_ui",
        "tab_color",
        "card_ui_chrome_color_difference",
    ]

    return (
        any(
            keyword in reason
            for keyword in reason_keywords
        )
        or any(
            keyword in rule
            for keyword in rule_keywords
        )
    )


def select_top_ui_bbox(
    detected_file_data: dict[str, Any],
    image: Image.Image,
) -> list[int]:
    top_bboxes: list[
        list[Any]
    ] = []

    for roi in get_detected_rois(
        detected_file_data
    ):
        bbox = roi.get("bbox")

        if not valid_bbox(bbox):
            continue

        try:
            x, y, w, h = [
                float(value)
                for value in bbox
            ]
        except (TypeError, ValueError):
            continue

        if w <= 0 or h <= 0:
            continue

        center_y = y + h / 2

        if (
            center_y
            <= image.height * 0.25
        ):
            top_bboxes.append(
                bbox
            )

    merged = merge_bboxes(
        top_bboxes
    )

    if merged:
        return merged

    return [
        0,
        0,
        image.width,
        round(
            image.height * 0.24
        ),
    ]


# =========================================================
# 9. 글자 / 선택값 색상 오류
# =========================================================
def is_text_color_error(
    selected_result: dict[str, Any],
) -> bool:
    rule = str(
        selected_result.get(
            "applied_rule",
            "",
        )
    ).lower()

    reason = get_reason_text(
        selected_result
    )

    explicit_rules = [
        "setting_chromatic_color_difference",
        "text_color",
        "selected_value_color",
        "selection_color",
        "font_color",
        "chromatic_text",
        "chromatic_color",
    ]

    if any(
        keyword in rule
        for keyword in explicit_rules
    ):
        return True

    reason_match = (
        (
            "색상" in reason
            or "색이" in reason
            or "색깔" in reason
        )
        and any(
            keyword in reason
            for keyword in [
                "글자",
                "텍스트",
                "선택값",
                "선택 값",
                "선택된 값",
                "설정",
            ]
        )
    )

    return reason_match


# =========================================================
# 10. 글자 색상 오류 bbox
# =========================================================
def select_text_color_bbox(
    reference_image: Image.Image,
    capture_image: Image.Image,
    detected_file_data: dict[str, Any],
) -> list[Any] | None:

    reference = np.array(
        reference_image.convert("RGB"),
        dtype=np.float32,
    )

    capture = np.array(
        capture_image.convert("RGB"),
        dtype=np.float32,
    )

    if reference.shape != capture.shape:
        return None

    # -----------------------------------------------------
    # 1차: detected ROI 안에서 색상 변화 찾기
    # -----------------------------------------------------
    candidates = []

    for roi in get_detected_rois(
        detected_file_data
    ):
        bbox = roi.get("bbox")

        if not valid_bbox(bbox):
            continue

        try:
            x, y, w, h = [
                int(round(float(value)))
                for value in bbox
            ]
        except (TypeError, ValueError):
            continue

        if w <= 0 or h <= 0:
            continue

        x1 = max(0, x)
        y1 = max(0, y)

        x2 = min(
            reference.shape[1],
            x + w,
        )

        y2 = min(
            reference.shape[0],
            y + h,
        )

        if x2 <= x1 or y2 <= y1:
            continue

        ref_crop = reference[
            y1:y2,
            x1:x2,
        ]

        cap_crop = capture[
            y1:y2,
            x1:x2,
        ]

        rgb_difference = float(
            np.mean(
                np.abs(
                    ref_crop
                    - cap_crop
                )
            )
        )

        ref_gray = (
            0.299
            * ref_crop[:, :, 0]
            + 0.587
            * ref_crop[:, :, 1]
            + 0.114
            * ref_crop[:, :, 2]
        )

        cap_gray = (
            0.299
            * cap_crop[:, :, 0]
            + 0.587
            * cap_crop[:, :, 1]
            + 0.114
            * cap_crop[:, :, 2]
        )

        brightness_difference = float(
            np.mean(
                np.abs(
                    ref_gray
                    - cap_gray
                )
            )
        )

        color_score = (
            rgb_difference
            - brightness_difference
            * 0.65
        )

        if color_score > 4.0:
            candidates.append(
                (
                    bbox,
                    color_score,
                )
            )

    if candidates:
        candidates.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return candidates[0][0]

    # -----------------------------------------------------
    # 2차:
    # ROI가 없어도 이미지 전체에서 색상 변화 직접 탐색
    # -----------------------------------------------------
    rgb_difference = np.abs(
        reference - capture
    )

    rgb_mean_difference = np.mean(
        rgb_difference,
        axis=2,
    )

    ref_gray = (
        0.299 * reference[:, :, 0]
        + 0.587 * reference[:, :, 1]
        + 0.114 * reference[:, :, 2]
    )

    cap_gray = (
        0.299 * capture[:, :, 0]
        + 0.587 * capture[:, :, 1]
        + 0.114 * capture[:, :, 2]
    )

    brightness_difference = np.abs(
        ref_gray
        - cap_gray
    )

    ref_max = np.max(
        reference,
        axis=2,
    )

    ref_min = np.min(
        reference,
        axis=2,
    )

    cap_max = np.max(
        capture,
        axis=2,
    )

    cap_min = np.min(
        capture,
        axis=2,
    )

    ref_chroma = (
        ref_max
        - ref_min
    )

    cap_chroma = (
        cap_max
        - cap_min
    )

    # 색 변화는 크지만
    # 밝기 변화는 상대적으로 작은 픽셀
    mask = (
        (rgb_mean_difference > 25)
        & (brightness_difference < 45)
        & (
            (ref_chroma > 25)
            | (cap_chroma > 25)
        )
    )

    height = reference.shape[0]
    width = reference.shape[1]

    # 가장자리 UI 아이콘 등의 색 변화 노이즈를 줄이기 위해
    # 좌우 아주 바깥쪽은 제외
    horizontal_margin = int(
        width * 0.03
    )

    mask[
        :,
        :horizontal_margin
    ] = False

    mask[
        :,
        width - horizontal_margin:
    ] = False

    ys, xs = np.where(
        mask
    )

    if len(xs) == 0:
        return None

    # -----------------------------------------------------
    # 색상 변화가 가장 밀집된 영역 찾기
    # -----------------------------------------------------
    cell_width = max(
        40,
        width // 20,
    )

    cell_height = max(
        30,
        height // 15,
    )

    best_count = 0
    best_cell = None

    for top in range(
        0,
        height,
        cell_height,
    ):
        for left in range(
            0,
            width,
            cell_width,
        ):
            right = min(
                width,
                left + cell_width,
            )

            bottom = min(
                height,
                top + cell_height,
            )

            cell_mask = mask[
                top:bottom,
                left:right,
            ]

            count = int(
                np.count_nonzero(
                    cell_mask
                )
            )

            if count > best_count:
                best_count = count

                best_cell = (
                    left,
                    top,
                    right,
                    bottom,
                )

    if (
        best_cell is None
        or best_count < 5
    ):
        return None

    left, top, right, bottom = (
        best_cell
    )

    search_left = max(
        0,
        left - cell_width,
    )

    search_top = max(
        0,
        top - cell_height,
    )

    search_right = min(
        width,
        right + cell_width,
    )

    search_bottom = min(
        height,
        bottom + cell_height,
    )

    local_mask = mask[
        search_top:search_bottom,
        search_left:search_right,
    ]

    local_y, local_x = np.where(
        local_mask
    )

    if len(local_x) == 0:
        return None

    x1 = (
        int(
            np.min(
                local_x
            )
        )
        + search_left
    )

    y1 = (
        int(
            np.min(
                local_y
            )
        )
        + search_top
    )

    x2 = (
        int(
            np.max(
                local_x
            )
        )
        + search_left
    )

    y2 = (
        int(
            np.max(
                local_y
            )
        )
        + search_top
    )

    padding = 12

    x1 = max(
        0,
        x1 - padding,
    )

    y1 = max(
        0,
        y1 - padding,
    )

    x2 = min(
        width - 1,
        x2 + padding,
    )

    y2 = min(
        height - 1,
        y2 + padding,
    )

    return [
        x1,
        y1,
        x2 - x1,
        y2 - y1,
    ]


# =========================================================
# 11. GUIDE IMAGE
# =========================================================
def select_guide_image_bbox(
    detected_file_data: dict[str, Any],
    image_width: int,
) -> list[Any] | None:

    candidates = []

    for roi in get_detected_rois(
        detected_file_data
    ):
        bbox = roi.get("bbox")

        if not valid_bbox(bbox):
            continue

        try:
            x, y, w, h = [
                float(value)
                for value in bbox
            ]
        except (TypeError, ValueError):
            continue

        if w <= 0 or h <= 0:
            continue

        center_x = x + w / 2

        if (
            center_x
            <= image_width * 0.55
        ):
            candidates.append(
                (
                    bbox,
                    safe_float(
                        roi.get(
                            "area_ratio",
                            0,
                        )
                    ),
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    selected = [
        item[0]
        for item in candidates[:3]
    ]

    return merge_bboxes(
        selected
    )


# =========================================================
# 12. OCR
# =========================================================
def get_ocr_rois(
    ocr_file_data: dict[str, Any],
) -> list[dict[str, Any]]:

    rois = ocr_file_data.get(
        "roi_results",
        [],
    )

    if not isinstance(
        rois,
        list,
    ):
        return []

    return [
        item
        for item in rois
        if isinstance(
            item,
            dict,
        )
    ]


# =========================================================
# 13. 텍스트 누락
# =========================================================
def find_missing_text_roi(
    ocr_file_data: dict[str, Any],
) -> str | None:

    candidates = []

    for item in get_ocr_rois(
        ocr_file_data
    ):

        roi_id = get_roi_id(
            item
        )

        if not roi_id:
            continue

        reference = item.get(
            "reference_ocr",
            {},
        )

        capture = item.get(
            "capture_ocr",
            {},
        )

        if not isinstance(
            reference,
            dict,
        ):
            reference = {}

        if not isinstance(
            capture,
            dict,
        ):
            capture = {}

        reference_text = str(
            reference.get(
                "text",
                "",
            )
        ).strip()

        capture_text = str(
            capture.get(
                "text",
                "",
            )
        ).strip()

        confidence = safe_float(
            reference.get(
                "mean_confidence",
                0,
            )
        )

        if (
            reference_text
            and not capture_text
        ):
            candidates.append(
                (
                    roi_id,
                    confidence,
                )
            )

    if candidates:
        candidates.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return candidates[0][0]

    return None


# =========================================================
# 14. Progress bar
# =========================================================
def get_progress_bbox(
    selected_result: dict[str, Any],
) -> list[Any] | None:

    evidence = selected_result.get(
        "evidence_summary",
        {},
    )

    if not isinstance(
        evidence,
        dict,
    ):
        return None

    progress = evidence.get(
        "progress_bar",
        {},
    )

    if not isinstance(
        progress,
        dict,
    ):
        return None

    for key in [
        "capture",
        "reference",
    ]:

        item = progress.get(
            key,
            {},
        )

        if isinstance(
            item,
            dict,
        ):
            bbox = item.get(
                "bbox"
            )

            if valid_bbox(
                bbox
            ):
                return bbox

    return None


# =========================================================
# 15. 밝기 저하
# =========================================================
def select_brightness_bbox(
    selected_result: dict[str, Any],
    ocr_file_data: dict[str, Any],
    bbox_map: dict[str, list[Any]],
) -> list[Any] | None:

    evidence = selected_result.get(
        "evidence_summary",
        {},
    )

    if not isinstance(
        evidence,
        dict,
    ):
        return None

    matched = evidence.get(
        "matched_text_brightness",
        {},
    )

    localized = evidence.get(
        "localized_text_brightness",
        {},
    )

    if not isinstance(
        matched,
        dict,
    ):
        matched = {}

    if not isinstance(
        localized,
        dict,
    ):
        localized = {}

    matched_count = int(
        safe_float(
            matched.get(
                "matched_roi_count",
                0,
            )
        )
    )

    localized_count = int(
        safe_float(
            localized.get(
                "roi_count",
                0,
            )
        )
    )

    candidates = []

    for item in get_ocr_rois(
        ocr_file_data
    ):

        compare = item.get(
            "ocr_compare",
            {},
        )

        if not isinstance(
            compare,
            dict,
        ):
            continue

        exact_match = bool(
            compare.get(
                "exact_match",
                False,
            )
        )

        compact_match = bool(
            compare.get(
                "compact_match",
                False,
            )
        )

        if not (
            exact_match
            or compact_match
        ):
            continue

        roi_id = get_roi_id(
            item
        )

        if (
            roi_id
            not in bbox_map
        ):
            continue

        candidates.append(
            (
                bbox_map[
                    roi_id
                ],
                safe_float(
                    item.get(
                        "area_ratio",
                        0,
                    )
                ),
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    if localized_count > 0:
        selected = [
            item[0]
            for item in candidates[
                :localized_count
            ]
        ]

        if len(selected) == 1:
            return selected[0]

        return merge_bboxes(
            selected
        )

    if matched_count > 0:
        selected = [
            item[0]
            for item in candidates[
                :matched_count
            ]
        ]

        return merge_bboxes(
            selected
        )

    return candidates[0][0]


# =========================================================
# 16. 가장 큰 ROI
# =========================================================
def get_largest_roi_bbox(
    detected_file_data: dict[str, Any],
) -> list[Any] | None:

    candidates = []

    for roi in get_detected_rois(
        detected_file_data
    ):

        bbox = roi.get(
            "bbox"
        )

        if not valid_bbox(
            bbox
        ):
            continue

        candidates.append(
            (
                bbox,
                safe_float(
                    roi.get(
                        "area_ratio",
                        0,
                    )
                ),
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    return candidates[0][0]


# =========================================================
# 17. 최종 시각화
# =========================================================
def create_visualization(
    reference_path: Path,
    capture_path: Path,
    selected_result: dict[str, Any],
    detected_file_data: dict[str, Any],
    ocr_file_data: dict[str, Any],
) -> tuple[
    Image.Image,
    str,
]:

    with Image.open(
        reference_path
    ) as source:
        reference_image = (
            source.convert(
                "RGB"
            )
        )

    with Image.open(
        capture_path
    ) as source:
        capture_image = (
            source.convert(
                "RGB"
            )
        )

    image = capture_image.copy()

    draw = ImageDraw.Draw(
        image
    )

    bbox_map = build_bbox_map(
        detected_file_data
    )

    rule = str(
        selected_result.get(
            "applied_rule",
            "",
        )
    ).lower()

    reason = get_reason_text(
        selected_result
    )

    category = str(
        selected_result.get(
            "category",
            "",
        )
    ).lower()

    # =====================================================
    # 1. 상단 UI / 탭
    # =====================================================
    if is_top_ui_error(
        selected_result
    ):

        bbox = select_top_ui_bbox(
            detected_file_data,
            image,
        )

        draw_bbox(
            draw,
            image,
            bbox,
            padding=6,
        )

        return (
            image,
            "TOP_UI_TAB_ERROR",
        )

    # =====================================================
    # 2. 글자 / 선택값 색상 오류
    # =====================================================
    if is_text_color_error(
        selected_result
    ):

        bbox = select_text_color_bbox(
            reference_image,
            capture_image,
            detected_file_data,
        )

        if bbox:
            draw_bbox(
                draw,
                image,
                bbox,
                padding=8,
            )

            return (
                image,
                "TEXT_COLOR_ERROR",
            )

    # =====================================================
    # 3. GUIDE IMAGE
    # =====================================================
    if (
        category == "guide_image"
        or "guide_image" in rule
        or (
            "안내 그림" in reason
            and "구조" in reason
        )
    ):

        bbox = select_guide_image_bbox(
            detected_file_data,
            image.width,
        )

        if bbox:
            draw_bbox(
                draw,
                image,
                bbox,
                padding=12,
            )

            return (
                image,
                "GUIDE_IMAGE_STRUCTURE",
            )

    # =====================================================
    # 4. 진행바
    # =====================================================
    if (
        "progress_bar" in rule
        or "진행 상태 바" in reason
    ):

        bbox = get_progress_bbox(
            selected_result
        )

        if bbox:
            draw_bbox(
                draw,
                image,
                bbox,
                padding=10,
            )

            return (
                image,
                "PROGRESS_BAR",
            )

    # =====================================================
    # 5. 텍스트 누락
    # =====================================================
    if (
        "missing_text" in rule
        or "텍스트 누락" in reason
    ):

        roi_id = find_missing_text_roi(
            ocr_file_data
        )

        if (
            roi_id
            and roi_id in bbox_map
        ):
            draw_bbox(
                draw,
                image,
                bbox_map[roi_id],
                padding=10,
            )

            return (
                image,
                "MISSING_TEXT",
            )

    # =====================================================
    # 6. 밝기 저하
    # =====================================================
    if (
        "brightness_loss" in rule
        or "밝기" in reason
        or "대비" in reason
    ):

        bbox = select_brightness_bbox(
            selected_result,
            ocr_file_data,
            bbox_map,
        )

        if bbox:
            draw_bbox(
                draw,
                image,
                bbox,
                padding=12,
            )

            return (
                image,
                "TEXT_BRIGHTNESS",
            )

    # =====================================================
    # 7. 그라데이션 / 일반 색상 영역
    # =====================================================
    if (
        "gradient" in rule
        or "color_difference" in rule
        or "그라데이션" in reason
    ):

        bbox = get_largest_roi_bbox(
            detected_file_data
        )

        if bbox:
            draw_bbox(
                draw,
                image,
                bbox,
                padding=10,
            )

            return (
                image,
                "GRADIENT_COLOR",
            )

    # =====================================================
    # 8. 이미지 / 구조
    # =====================================================
    if any(
        keyword in rule
        for keyword in [
            "image",
            "structure",
            "ssim",
        ]
    ):

        bbox = get_largest_roi_bbox(
            detected_file_data
        )

        if bbox:
            draw_bbox(
                draw,
                image,
                bbox,
                padding=10,
            )

            return (
                image,
                "IMAGE_STRUCTURE",
            )

    # =====================================================
    # 9. fallback
    # =====================================================
    bbox = get_largest_roi_bbox(
        detected_file_data
    )

    if bbox:
        draw_bbox(
            draw,
            image,
            bbox,
            padding=10,
        )

        return (
            image,
            "LARGEST_DIFF_FALLBACK",
        )

    draw_full_border(
        draw,
        image,
    )

    return (
        image,
        "FULL_BORDER_FALLBACK",
    )


# =========================================================
# 18. 시나리오 처리
# =========================================================
def process_scenario(
    scenario_name: str,
    output_name: str,
) -> tuple[
    int,
    int,
]:

    result_dir = (
        RESULT_SCENARIOS_DIR
        / scenario_name
    )

    data_dir = (
        DATA_SCENARIOS_DIR
        / scenario_name
    )

    inspection_data = load_json(
        result_dir
        / "inspection_results.json"
    )

    detected_data = load_json(
        result_dir
        / "detected_rois.json"
    )

    ocr_data = load_json(
        result_dir
        / "ocr_results.json"
    )

    inspection_results = (
        inspection_data.get(
            "results",
            {},
        )
    )

    detected_results = (
        detected_data.get(
            "results",
            {},
        )
    )

    ocr_results = (
        ocr_data.get(
            "results",
            {},
        )
    )

    if not isinstance(
        inspection_results,
        dict,
    ):
        raise ValueError(
            "inspection_results.json 구조 오류"
        )

    if not isinstance(
        detected_results,
        dict,
    ):
        detected_results = {}

    if not isinstance(
        ocr_results,
        dict,
    ):
        ocr_results = {}

    output_dir = (
        OUTPUT_ROOT
        / output_name
    )

    if output_dir.exists():
        shutil.rmtree(
            output_dir
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    created = 0
    skipped = 0

    print()
    print(
        f"===== {output_name} 생성 시작 ====="
    )

    for (
        file_name,
        selected_result,
    ) in inspection_results.items():

        if not isinstance(
            selected_result,
            dict,
        ):
            continue

        if normalize_status(
            selected_result.get(
                "final_status"
            )
        ) != "FAIL":
            continue

        reference_path = (
            data_dir
            / "reference"
            / file_name
        )

        capture_path = (
            data_dir
            / "capture"
            / file_name
        )

        if not reference_path.exists():

            print(
                f"[SKIP] "
                f"Reference 없음: "
                f"{file_name}"
            )

            skipped += 1
            continue

        if not capture_path.exists():

            print(
                f"[SKIP] "
                f"Capture 없음: "
                f"{file_name}"
            )

            skipped += 1
            continue

        detected_file_data = (
            detected_results.get(
                file_name,
                {},
            )
        )

        ocr_file_data = (
            ocr_results.get(
                file_name,
                {},
            )
        )

        if not isinstance(
            detected_file_data,
            dict,
        ):
            detected_file_data = {}

        if not isinstance(
            ocr_file_data,
            dict,
        ):
            ocr_file_data = {}

        image, method = create_visualization(
            reference_path=reference_path,
            capture_path=capture_path,
            selected_result=selected_result,
            detected_file_data=(
                detected_file_data
            ),
            ocr_file_data=(
                ocr_file_data
            ),
        )

        output_path = (
            output_dir
            / file_name
        )

        image.save(
            output_path
        )

        print(
            f"[CREATE] "
            f"{file_name} "
            f"RULE="
            f"{selected_result.get('applied_rule', '-')} "
            f"METHOD={method}"
        )

        created += 1

    print(
        f"{output_name}: "
        f"{created}개 생성"
    )

    return (
        created,
        skipped,
    )


# =========================================================
# 19. 전체 실행
# =========================================================
def main() -> None:

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_created = 0
    total_skipped = 0

    for (
        scenario_name,
        output_name,
    ) in SCENARIOS.items():

        try:
            created, skipped = (
                process_scenario(
                    scenario_name,
                    output_name,
                )
            )

            total_created += created
            total_skipped += skipped

        except FileNotFoundError as error:
            print(
                f"[SCENARIO SKIP] "
                f"{error}"
            )

    print()
    print(
        "=============================="
    )
    print("전체 완료")
    print(
        f"총 생성 이미지: "
        f"{total_created}개"
    )
    print(
        f"총 건너뜀: "
        f"{total_skipped}개"
    )
    print(
        f"저장 위치: "
        f"{OUTPUT_ROOT}"
    )
    print(
        "=============================="
    )


if __name__ == "__main__":
    main()