"""Model C / Model D 데모 전용 - 계산 알고리즘 없이 고정 결과만 반환.

이미지를 열어서 분석하지 않는다(OpenCV 등 이미지 처리 라이브러리를
전혀 쓰지 않는다). Reference/Capture 파일명이 매칭되는 화면마다
호출 시 지정한 final_status(PASS 또는 FAIL)를 그대로 기록만 한다.

결과 파일(inspection_results.json)의 최상위 구조와 항목별 필드명은
decision_engine.py의 decide_one_item() 출력과 동일한 모양을 유지해서,
결과를 읽는 화면 쪽 코드를 수정하지 않아도 되도록 했다.
"""

import json
from pathlib import Path

try:
    from modules.path_config import PROJECT_ROOT
except ModuleNotFoundError:
    from path_config import PROJECT_ROOT


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def _to_project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _image_names(directory: Path):
    if not directory.exists():
        return set()
    return {
        p.name for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    }


def _build_item(file_name: str, reference_path: Path, capture_path: Path,
                 final_status: str, enabled_checks: dict):
    screen_id = Path(file_name).stem

    if final_status == "FAIL":
        final_reasons = ["진행 상태 바의 채워진 길이 차이가 허용 기준을 초과함."]
        applied_rule = "demo_forced_fail"
        diff_roi_count = 1
        total_diff_area_ratio = 0.052
        overall_ssim = 0.913
        minimum_roi_ssim = 0.417
    else:
        final_reasons = ["데모 모델 설정에 따라 PASS로 고정됨"]
        applied_rule = "demo_forced_pass"
        diff_roi_count = 0
        total_diff_area_ratio = 0.004
        overall_ssim = 0.986
        minimum_roi_ssim = 0.958

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": "status_time",
        "profile": "status_time_profile",
        "reference_image": _to_project_relative(reference_path),
        "capture_image": _to_project_relative(capture_path),
        "expected_result": "",
        "expected_binary_result": "UNKNOWN",
        "memo": "",
        "final_status": final_status,
        "applied_rule": applied_rule,
        "final_reasons": final_reasons,
        "diff_summary": {
            "diff_roi_count": diff_roi_count,
            "total_diff_area_ratio": total_diff_area_ratio,
        },
        "evidence_summary": {
            "overall_ssim": overall_ssim,
            "minimum_roi_ssim": minimum_roi_ssim,
            "confirmed_missing_text_count": 0,
            "bidirectional_text_presence_count": 0,
            "high_confidence_text_mismatch_count": 0,
            "high_confidence_spacing_mismatch_count": 0,
            "matched_text_brightness": {"matched_roi_count": 0, "mean_brightness_loss": 0.0},
            "localized_text_brightness": {"roi_count": 0, "max_brightness_loss": 0.0},
            "progress_bar": {"reference": {"found": False, "fill_width_ratio": None, "bbox": None},
                              "capture": {"found": False, "fill_width_ratio": None, "bbox": None},
                              "fill_delta": None},
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


def run_demo_fixed_result_inspection(
    reference_dir: Path,
    capture_dir: Path,
    results_dir: Path,
    final_status: str,
    enabled_checks: dict,
) -> dict:
    """
    Model C / Model D 데모용. 계산 없이 final_status를 그대로 기록한다.

    final_status: "PASS" 또는 "FAIL"
    """
    if final_status not in ("PASS", "FAIL"):
        raise ValueError(f"final_status는 PASS 또는 FAIL이어야 합니다: {final_status}")

    reference_dir = Path(reference_dir)
    capture_dir = Path(capture_dir)
    results_dir = Path(results_dir)

    reference_names = _image_names(reference_dir)
    capture_names = _image_names(capture_dir)
    matched_names = sorted(reference_names & capture_names)

    if not matched_names:
        raise ValueError(
            "같은 파일명을 가진 reference/capture 쌍이 없습니다. "
            f"reference={reference_dir}, capture={capture_dir}"
        )

    results = {}
    for file_name in matched_names:
        results[file_name] = _build_item(
            file_name=file_name,
            reference_path=reference_dir / file_name,
            capture_path=capture_dir / file_name,
            final_status=final_status,
            enabled_checks=enabled_checks,
        )

    pass_count = sum(1 for item in results.values() if item["final_status"] == "PASS")
    fail_count = sum(1 for item in results.values() if item["final_status"] == "FAIL")

    output = {
        "summary": {
            "total_items": len(matched_names),
            "processed_count": len(results),
            "error_count": 0,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "errors": [],
        },
        "binary_policy": {
            "enabled_checks": enabled_checks,
            "note": "Model C/D 데모 전용 고정 결과 (계산 알고리즘 미사용)",
        },
        "results": results,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / "inspection_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output
