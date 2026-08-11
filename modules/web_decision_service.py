"""Streamlit 등 웹 UI가 판정 엔진을 간단히 호출하도록 만든 연결 모듈.

OCR, SSIM, ROI 검출 결과는 이미 생성된 JSON을 읽어 재사용한다. 웹 UI가
전달한 여섯 개의 옵션은 메모리 안에서만 적용하며 설정 파일이나 결과 파일을
수정하지 않는다.
"""

from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from time import perf_counter

try:
    from modules.decision_engine import (
        OCR_RESULTS_PATH,
        SSIM_RESULTS_PATH,
        decide_one_item,
        load_json,
        load_reference_registry,
    )
    from modules.path_config import (
        CAPTURE_DIR,
        DETECTED_ROIS_PATH,
        INSPECTION_PROFILES_PATH,
        PROJECT_ROOT,
        REFERENCE_DIR,
        REFERENCE_REGISTRY_PATH,
    )
except ModuleNotFoundError:
    from decision_engine import (
        OCR_RESULTS_PATH,
        SSIM_RESULTS_PATH,
        decide_one_item,
        load_json,
        load_reference_registry,
    )
    from path_config import (
        CAPTURE_DIR,
        DETECTED_ROIS_PATH,
        INSPECTION_PROFILES_PATH,
        PROJECT_ROOT,
        REFERENCE_DIR,
        REFERENCE_REGISTRY_PATH,
    )


SCHEMA_VERSION = "1.0"

OPTION_DEFINITIONS = (
    {
        "key": "text_content",
        "label": "텍스트 내용 검사",
        "description": "글자 누락·교체와 설정값 숫자 차이를 판정합니다.",
        "default": True,
    },
    {
        "key": "text_spacing",
        "label": "띄어쓰기 검사",
        "description": "글자는 같아도 의미를 바꾸는 띄어쓰기 차이를 판정합니다.",
        "default": True,
    },
    {
        "key": "image_structure",
        "label": "그림·배치 검사",
        "description": "그림, 컴포넌트, 팝업 배치의 큰 구조 차이를 판정합니다.",
        "default": True,
    },
    {
        "key": "gradient_color",
        "label": "그라데이션 색상 검사",
        "description": "카드와 팝업의 부드러운 색상·그라데이션 차이를 판정합니다.",
        "default": True,
    },
    {
        "key": "text_brightness",
        "label": "텍스트 밝기 검사",
        "description": "문구는 같지만 글자가 지나치게 흐리거나 어두운 경우를 판정합니다.",
        "default": True,
    },
    {
        "key": "progress_bar",
        "label": "게이지 검사",
        "description": "상태 화면의 진행 바가 채워진 정도 차이를 판정합니다.",
        "default": True,
    },
)

OPTION_KEYS = tuple(option["key"] for option in OPTION_DEFINITIONS)


class OptionValidationError(ValueError):
    """웹에서 전달된 옵션 형식이 잘못된 경우의 오류."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def get_option_definitions():
    """UI가 체크박스를 만들 때 사용할 여섯 개 옵션 정보를 반환한다."""
    return [dict(option) for option in OPTION_DEFINITIONS]


@lru_cache(maxsize=1)
def _load_inputs():
    diff_document = load_json(DETECTED_ROIS_PATH, "detected_rois.json")
    ssim_document = load_json(SSIM_RESULTS_PATH, "ssim_results.json")
    ocr_document = load_json(OCR_RESULTS_PATH, "ocr_results.json")
    profile_document = load_json(
        INSPECTION_PROFILES_PATH,
        "inspection_profiles.json",
    )

    diff_items = diff_document.get("results", {})
    ssim_items = ssim_document.get("results", {})
    ocr_items = ocr_document.get("results", {})
    binary_policy = profile_document.get("binary_policy", {})

    if not isinstance(diff_items, dict):
        raise ValueError("detected_rois.json의 results가 객체 형식이 아닙니다.")
    if not isinstance(ssim_items, dict):
        raise ValueError("ssim_results.json의 results가 객체 형식이 아닙니다.")
    if not isinstance(ocr_items, dict):
        raise ValueError("ocr_results.json의 results가 객체 형식이 아닙니다.")
    if not isinstance(binary_policy, dict):
        raise ValueError("inspection_profiles.json에 binary_policy가 없습니다.")

    return {
        "diff_items": diff_items,
        "ssim_items": ssim_items,
        "ocr_items": ocr_items,
        "binary_policy": binary_policy,
        "registry": load_reference_registry(),
    }


def clear_cache():
    """결과 JSON이나 설정 파일을 새로 만들었을 때 메모리 캐시를 비운다."""
    _load_inputs.cache_clear()


def _default_options(binary_policy):
    configured = binary_policy.get("enabled_checks", {})
    return {
        option["key"]: bool(configured.get(option["key"], option["default"]))
        for option in OPTION_DEFINITIONS
    }


def _normalize_options(options, binary_policy):
    normalized = _default_options(binary_policy)

    if options is None:
        return normalized
    if not isinstance(options, dict):
        raise OptionValidationError(
            "INVALID_OPTIONS_TYPE",
            "options는 {'text_content': True}와 같은 dict여야 합니다.",
        )

    unknown_keys = sorted(set(options) - set(OPTION_KEYS))
    if unknown_keys:
        raise OptionValidationError(
            "UNKNOWN_OPTION",
            "지원하지 않는 옵션입니다: " + ", ".join(unknown_keys),
        )

    for key, value in options.items():
        if type(value) is not bool:
            raise OptionValidationError(
                "INVALID_OPTION_VALUE",
                f"{key} 값은 반드시 True 또는 False여야 합니다.",
            )
        normalized[key] = value

    return normalized


def _web_path(value):
    if not value:
        return ""
    return Path(str(value)).as_posix()


def resolve_media_path(relative_path):
    """응답의 상대 이미지 경로를 st.image에서 쓸 실제 경로로 바꾼다."""
    if not relative_path:
        return ""
    return str(PROJECT_ROOT / Path(relative_path))


def _error_response(code, message, elapsed_seconds=0.0):
    return {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "error_code": code,
        "message": message,
        "active_options": {},
        "summary": {
            "total": 0,
            "processed": 0,
            "error_count": 1,
            "pass": 0,
            "fail": 0,
        },
        "category_summary": [],
        "items": [],
        "errors": [{"file_name": "", "message": message}],
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def health_check():
    """배포 전에 필요한 파일과 73개 입력의 연결 상태를 확인한다."""
    required_paths = {
        "reference_images": REFERENCE_DIR,
        "capture_images": CAPTURE_DIR,
        "detected_rois": DETECTED_ROIS_PATH,
        "ssim_results": SSIM_RESULTS_PATH,
        "ocr_results": OCR_RESULTS_PATH,
        "inspection_profiles": INSPECTION_PROFILES_PATH,
        "reference_registry": REFERENCE_REGISTRY_PATH,
    }
    missing_paths = [
        str(path) for path in required_paths.values() if not Path(path).exists()
    ]

    if missing_paths:
        return {
            "ready": False,
            "total_items": 0,
            "missing_files": missing_paths,
            "data_errors": [],
            "message": "판정에 필요한 파일 또는 폴더가 없습니다.",
        }

    try:
        data = _load_inputs()
    except Exception as exc:
        return {
            "ready": False,
            "total_items": 0,
            "missing_files": [],
            "data_errors": [str(exc)],
            "message": "판정 입력 파일을 읽지 못했습니다.",
        }

    file_names = set(data["diff_items"])
    registry_names = set(data["registry"])
    ssim_names = set(data["ssim_items"])
    ocr_names = set(data["ocr_items"])
    data_errors = []

    for label, missing_names in (
        ("reference_registry", file_names - registry_names),
        ("ssim_results", file_names - ssim_names),
        ("ocr_results", file_names - ocr_names),
    ):
        if missing_names:
            data_errors.append(f"{label} 누락: " + ", ".join(sorted(missing_names)))

    return {
        "ready": not data_errors,
        "total_items": len(file_names),
        "missing_files": [],
        "data_errors": data_errors,
        "message": (
            "웹 재판정을 실행할 준비가 되었습니다."
            if not data_errors
            else "입력 JSON 사이에 누락된 화면이 있습니다."
        ),
    }


def evaluate(options=None, progress_callback=None):
    """여섯 개 옵션으로 73개 화면을 빠르게 PASS/FAIL 재판정한다.

    Args:
        options: OPTION_KEYS 중 필요한 값만 담은 dict. 생략한 값은 설정 파일의
            기본값을 사용한다.
        progress_callback: 선택 사항. ``callback(current, total, message)``
            형태의 함수를 전달하면 화면별 진행률을 받을 수 있다.

    Returns:
        Streamlit에서 바로 사용할 수 있는 dict. 파일은 새로 쓰지 않는다.
    """
    started_at = perf_counter()

    try:
        data = _load_inputs()
        active_options = _normalize_options(options, data["binary_policy"])
    except OptionValidationError as exc:
        return _error_response(
            exc.code,
            str(exc),
            perf_counter() - started_at,
        )
    except Exception as exc:
        return _error_response(
            "INPUT_LOAD_ERROR",
            f"판정 입력을 읽지 못했습니다: {exc}",
            perf_counter() - started_at,
        )

    binary_policy = deepcopy(data["binary_policy"])
    binary_policy.setdefault("enabled_checks", {}).update(active_options)

    ordered_files = sorted(data["diff_items"])
    total = len(ordered_files)
    result_items = []
    errors = []
    status_counts = {"PASS": 0, "FAIL": 0}
    category_counts = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0})

    if progress_callback is not None:
        progress_callback(0, total, "판정을 시작합니다.")

    for current, file_name in enumerate(ordered_files, start=1):
        try:
            decision = decide_one_item(
                file_name,
                data["diff_items"][file_name],
                data["ssim_items"].get(file_name, {}),
                data["ocr_items"].get(file_name, {}),
                data["registry"].get(file_name, {}),
                binary_policy,
            )

            status = decision["final_status"]
            category = decision["category"]
            status_counts[status] += 1
            category_counts[category]["total"] += 1
            category_counts[category][status.lower()] += 1

            result_items.append(
                {
                    "screen_id": decision["screen_id"],
                    "file_name": decision["file_name"],
                    "category": category,
                    "status": status,
                    "reason": " | ".join(decision["final_reasons"]),
                    "reasons": list(decision["final_reasons"]),
                    "applied_rule": decision["applied_rule"],
                    "images": {
                        "reference": _web_path(decision["reference_image"]),
                        "capture": _web_path(decision["capture_image"]),
                        "diff": _web_path(
                            decision.get("debug_images", {}).get("diff_debug", "")
                        ),
                    },
                    "metrics": {
                        "diff_roi_count": decision["diff_summary"]["diff_roi_count"],
                        "total_diff_area_ratio": decision["diff_summary"][
                            "total_diff_area_ratio"
                        ],
                        "overall_ssim": decision["evidence_summary"]["overall_ssim"],
                        "minimum_roi_ssim": decision["evidence_summary"][
                            "minimum_roi_ssim"
                        ],
                    },
                    "evidence": decision["evidence_summary"],
                }
            )
        except Exception as exc:
            errors.append({"file_name": file_name, "message": str(exc)})

        if progress_callback is not None:
            progress_callback(
                current,
                total,
                f"{current}/{total} 화면 판정 중",
            )

    category_summary = [
        {"category": category, **counts}
        for category, counts in sorted(category_counts.items())
    ]

    return {
        "ok": not errors,
        "schema_version": SCHEMA_VERSION,
        "message": (
            "재판정이 완료되었습니다."
            if not errors
            else "일부 화면에서 오류가 발생했습니다."
        ),
        "active_options": active_options,
        "summary": {
            "total": total,
            "processed": len(result_items),
            "error_count": len(errors),
            "pass": status_counts["PASS"],
            "fail": status_counts["FAIL"],
        },
        "category_summary": category_summary,
        "items": result_items,
        "errors": errors,
        "elapsed_seconds": round(perf_counter() - started_at, 3),
    }


if __name__ == "__main__":
    check = health_check()
    print(check)
    if check["ready"]:
        result = evaluate()
        print(result["summary"])
        print(f"elapsed_seconds={result['elapsed_seconds']}")
