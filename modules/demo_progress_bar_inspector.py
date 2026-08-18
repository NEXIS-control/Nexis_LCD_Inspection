"""Model C / Model D 데모 전용 경량 판정 스크립트.

기존 pair_manager -> diff_detector -> ssim_checker -> ocr_checker ->
decision_engine 파이프라인을 전혀 거치지 않는다. 오직 "진행바가 채워진
길이"만 비교해서 PASS/FAIL을 결정하는 '껍데기' 판정 엔진이다.

결과 파일(inspection_results.json)의 최상위 구조와 항목별 필드명은
기존 decision_engine.py의 decide_one_item() 출력과 최대한 동일하게
맞춰서, 결과를 읽는 화면 쪽 코드를 수정하지 않아도 되도록 했다.
"""

import json
from pathlib import Path

import cv2
import numpy as np

try:
    from modules.path_config import PROJECT_ROOT
except ModuleNotFoundError:
    from path_config import PROJECT_ROOT


# ============================================================
# Unicode-safe image IO (한글 경로 대응)
# ============================================================

def _read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {path}")
    return image


def _to_project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        # PROJECT_ROOT 바깥 경로일 경우 절대경로 문자열로라도 반환
        return str(path)


# ============================================================
# 진행바 검출 (decision_engine.find_progress_bar_fill과 동일한 방식)
# ============================================================

DEFAULT_RULES = {
    "progress_bar_saturation_min": 120,
    "progress_bar_value_min": 100,
    "progress_bar_min_width_ratio": 0.06,
    "progress_bar_max_height": 60,
    "progress_bar_min_aspect_ratio": 4.0,
    "progress_bar_min_y_ratio": 0.0,   # 화면 어디에 있어도 찾도록 완화
    "progress_bar_fill_delta_fail": 0.025,
}


def _find_progress_bar_fill(image, rules: dict):
    image_height, image_width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    saturation_min = int(rules["progress_bar_saturation_min"])
    value_min = int(rules["progress_bar_value_min"])
    min_width_ratio = float(rules["progress_bar_min_width_ratio"])
    max_height = int(rules["progress_bar_max_height"])
    min_aspect_ratio = float(rules["progress_bar_min_aspect_ratio"])
    min_y_ratio = float(rules["progress_bar_min_y_ratio"])

    mask = (
        (hsv[:, :, 1] >= saturation_min) & (hsv[:, :, 2] >= value_min)
    ).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        width_ratio = w / image_width
        aspect_ratio = w / max(h, 1)

        if (
            width_ratio >= min_width_ratio
            and h <= max_height
            and aspect_ratio >= min_aspect_ratio
            and y / image_height >= min_y_ratio
        ):
            candidates.append(
                {
                    "bbox": [int(x), int(y), int(w), int(h)],
                    "fill_width_ratio": round(float(width_ratio), 6),
                }
            )

    if not candidates:
        return {"found": False, "fill_width_ratio": None, "bbox": None}

    best = max(candidates, key=lambda item: item["fill_width_ratio"])
    return {"found": True, **best}


def _compare_progress_bar(reference_image, capture_image, rules: dict):
    reference_bar = _find_progress_bar_fill(reference_image, rules)
    capture_bar = _find_progress_bar_fill(capture_image, rules)

    if reference_bar["found"] and capture_bar["found"]:
        delta = abs(reference_bar["fill_width_ratio"] - capture_bar["fill_width_ratio"])
    else:
        delta = None

    return {
        "reference": reference_bar,
        "capture": capture_bar,
        "fill_delta": round(float(delta), 6) if delta is not None else None,
    }


# ============================================================
# 파일 매칭 (reference_dir / capture_dir 안에서 동일 파일명끼리)
# ============================================================

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def _image_names(directory: Path):
    if not directory.exists():
        return set()
    return {
        p.name for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    }


# ============================================================
# 항목 하나 판정
# ============================================================

def _decide_one_file(file_name: str, reference_path: Path, capture_path: Path,
                      enabled_checks: dict, rules: dict):
    reference_image = _read_image(reference_path)
    capture_image = _read_image(capture_path)

    progress_bar_evidence = _compare_progress_bar(reference_image, capture_image, rules)
    fill_delta = progress_bar_evidence["fill_delta"]

    final_status = "PASS"
    final_reasons = []
    applied_rule = "demo_default_pass"

    progress_bar_enabled = bool(enabled_checks.get("progress_bar", True))

    if (
        progress_bar_enabled
        and fill_delta is not None
        and fill_delta >= float(rules["progress_bar_fill_delta_fail"])
    ):
        final_status = "FAIL"
        final_reasons.append(
            f"진행 상태 바의 채워진 길이 차이가 허용 기준을 초과함: delta={fill_delta}"
        )
        applied_rule = "demo_status_progress_bar_difference"
    elif not progress_bar_enabled:
        final_reasons.append("진행 상태 표시 항목이 미체크되어 판정에서 제외됨")
        applied_rule = "demo_progress_bar_check_disabled"
    else:
        final_reasons.append("진행 상태 바 차이가 허용 기준 이내임")

    screen_id = Path(file_name).stem

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": "status_time_demo",
        "profile": "demo_progress_bar_profile",
        "reference_image": _to_project_relative(reference_path),
        "capture_image": _to_project_relative(capture_path),
        "expected_result": "",
        "expected_binary_result": "UNKNOWN",
        "memo": "",
        "final_status": final_status,
        "applied_rule": applied_rule,
        "final_reasons": final_reasons,
        "diff_summary": {
            "diff_roi_count": 1 if fill_delta is not None else 0,
            "total_diff_area_ratio": fill_delta if fill_delta is not None else 0.0,
        },
        "evidence_summary": {
            "overall_ssim": None,
            "minimum_roi_ssim": 1.0,
            "confirmed_missing_text_count": 0,
            "bidirectional_text_presence_count": 0,
            "high_confidence_text_mismatch_count": 0,
            "high_confidence_spacing_mismatch_count": 0,
            "matched_text_brightness": {"matched_roi_count": 0, "mean_brightness_loss": 0.0},
            "localized_text_brightness": {"roi_count": 0, "max_brightness_loss": 0.0},
            "progress_bar": progress_bar_evidence,
            "gradient_color": {
                "reference_smooth_color_area_ratio": 0.0,
                "capture_smooth_color_area_ratio": 0.0,
                "smooth_color_area_delta": 0.0,
                "color_histogram_distance": 0.0,
                "max_smooth_color_area_ratio": 0.0,
            },
            "localized_visual": {"roi_metrics": []},
            "chromatic_color": {"overall_diff_area_ratio": 0.0, "top_band_diff_area_ratio": 0.0},
            "largest_roi_structure": {"roi_id": "", "area_ratio": 0.0, "ssim_score": 1.0},
        },
        "roi_decision_summary": {
            "pass_count": 1 if final_status == "PASS" else 0,
            "fail_count": 1 if final_status == "FAIL" else 0,
        },
        "roi_decisions": [],
        "debug_images": {"diff_debug": ""},
    }


# ============================================================
# 메인 진입점 : web.py에서 직접 호출
# ============================================================

def run_demo_progress_bar_inspection(
    reference_dir: Path,
    capture_dir: Path,
    results_dir: Path,
    enabled_checks: dict,
    fill_delta_fail: float = 0.025,
) -> dict:
    """
    Model C / Model D 데모용 진행바 전용 판정을 실행하고
    results_dir/inspection_results.json 을 저장한다.

    기존 decision_engine.py, inspector.py는 전혀 호출하지 않는다.
    """
    reference_dir = Path(reference_dir)
    capture_dir = Path(capture_dir)
    results_dir = Path(results_dir)

    rules = dict(DEFAULT_RULES)
    rules["progress_bar_fill_delta_fail"] = float(fill_delta_fail)

    reference_names = _image_names(reference_dir)
    capture_names = _image_names(capture_dir)
    matched_names = sorted(reference_names & capture_names)

    if not matched_names:
        raise ValueError(
            "같은 파일명을 가진 reference/capture 쌍이 없습니다. "
            f"reference={reference_dir}, capture={capture_dir}"
        )

    results = {}
    errors = []

    for file_name in matched_names:
        try:
            results[file_name] = _decide_one_file(
                file_name=file_name,
                reference_path=reference_dir / file_name,
                capture_path=capture_dir / file_name,
                enabled_checks=enabled_checks,
                rules=rules,
            )
        except Exception as error:
            errors.append({"file_name": file_name, "error": str(error)})

    pass_count = sum(1 for item in results.values() if item["final_status"] == "PASS")
    fail_count = sum(1 for item in results.values() if item["final_status"] == "FAIL")

    output = {
        "summary": {
            "total_items": len(matched_names),
            "processed_count": len(results),
            "error_count": len(errors),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "errors": errors,
        },
        "binary_policy": {
            "enabled_checks": enabled_checks,
            "note": "Model C/D 데모 전용 경량 엔진 결과 (실제 판독 파이프라인 미사용)",
        },
        "results": results,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / "inspection_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output