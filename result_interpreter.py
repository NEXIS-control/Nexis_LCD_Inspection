from __future__ import annotations

from typing import Any


# =========================================================
# 1. 오류 코드별 사용자 안내 문구
# =========================================================
ERROR_MESSAGES: dict[str, str] = {
    "TEXT_MISMATCH": (
        "기준 화면과 촬영 화면의 문자 내용이 서로 다릅니다."
    ),
    "TEXT_MISSING": (
        "기준 화면에 있어야 하는 문자가 촬영 화면에서 검출되지 않았습니다."
    ),
    "TEXT_EXTRA": (
        "기준 화면에 없는 추가 문자가 촬영 화면에서 검출되었습니다."
    ),
    "TEXT_POSITION_ERROR": (
        "문자 위치가 기준 위치에서 허용 범위를 벗어났습니다."
    ),
    "TEXT_POSITION_NEAR_LIMIT": (
        "문자 위치가 허용 한계에 가까워 추가 확인이 필요합니다."
    ),
    "OCR_LOW_CONFIDENCE": (
        "문자 인식 신뢰도가 낮아 사람이 직접 확인해야 합니다."
    ),
    "IMAGE_SIMILARITY_LOW": (
        "기준 이미지와 촬영 이미지의 유사도가 허용 기준보다 낮습니다."
    ),
    "SSIM_LOW": (
        "화면 구조의 유사도가 기준값보다 낮습니다."
    ),
    "BRIGHTNESS_ERROR": (
        "촬영 화면의 밝기가 기준 범위를 벗어났습니다."
    ),
    "COLOR_ERROR": (
        "화면 색상이 기준 범위와 다릅니다."
    ),
    "ICON_MISSING": (
        "기준 화면에 있어야 하는 아이콘이 검출되지 않았습니다."
    ),
    "ICON_MISMATCH": (
        "검출된 아이콘이 기준 아이콘과 일치하지 않습니다."
    ),
    "ICON_POSITION_ERROR": (
        "아이콘 위치가 기준 위치에서 허용 범위를 벗어났습니다."
    ),
    "ROI_MISSING": (
        "검사해야 할 화면 영역을 찾지 못했습니다."
    ),
    "ROI_SIZE_ERROR": (
        "검사 영역의 크기가 기준 범위와 다릅니다."
    ),
    "SCREEN_STATE_ERROR": (
        "현재 화면 상태가 예상된 정상 상태와 다릅니다."
    ),
    "INVALID_TRANSITION": (
        "화면 전환 순서가 정상 상태 전이 규칙과 일치하지 않습니다."
    ),
    "PROCESSING_DELAY": (
        "화면 전환 또는 분석 처리 시간이 허용 시간을 초과했습니다."
    ),
    "UNKNOWN_ERROR": (
        "정의되지 않은 검사 이상이 발견되었습니다."
    ),
}


# =========================================================
# 2. 분석 모듈 이름 변환
# =========================================================
MODULE_NAMES: dict[str, str] = {
    "text": "문자 검사",
    "ocr": "문자 인식 검사",
    "visual": "화면 유사도 검사",
    "image": "이미지 비교 검사",
    "ssim": "SSIM 유사도 검사",
    "icon": "아이콘 검사",
    "position": "위치 검사",
    "brightness": "밝기 검사",
    "color": "색상 검사",
    "roi": "검사 영역 분석",
    "state": "화면 상태 검사",
    "fsm": "화면 전환 검사",
    "timing": "처리 시간 검사",
    "system": "시스템 검사",
}


# =========================================================
# 3. 오류 코드 설명 반환
# =========================================================
def get_error_message(error_code: str) -> str:
    """
    오류 코드에 해당하는 사용자 안내 문구를 반환한다.
    """
    normalized_code = str(error_code).strip().upper()

    return ERROR_MESSAGES.get(
        normalized_code,
        ERROR_MESSAGES["UNKNOWN_ERROR"],
    )


# =========================================================
# 4. 모듈 이름 반환
# =========================================================
def get_module_name(module: str) -> str:
    """
    분석 모듈의 영문 이름을 한글 표시 이름으로 변환한다.
    """
    normalized_module = str(module).strip().lower()

    return MODULE_NAMES.get(
        normalized_module,
        module if module else "알 수 없는 검사",
    )


# =========================================================
# 5. 측정값 설명 생성
# =========================================================
def build_measurement_description(
    metric_name: str | None,
    measured_value: Any,
    reference_value: Any,
    tolerance: Any,
    unit: str | None,
) -> str:
    """
    측정값, 기준값, 허용 기준을 한 문장으로 만든다.
    """
    display_metric = metric_name or "측정 지표"
    display_unit = unit or ""

    measured_text = (
        "-"
        if measured_value is None
        else f"{measured_value}{display_unit}"
    )

    reference_text = (
        "-"
        if reference_value is None
        else f"{reference_value}{display_unit}"
    )

    tolerance_text = (
        "-"
        if tolerance is None
        else f"{tolerance}{display_unit}"
    )

    return (
        f"{display_metric}의 측정값은 {measured_text}이며, "
        f"기준값은 {reference_text}, "
        f"허용 기준은 {tolerance_text}입니다."
    )


# =========================================================
# 6. 개별 finding 해석
# =========================================================
def interpret_finding(
    finding: dict[str, Any],
) -> dict[str, Any]:
    """
    JSON finding 한 개를 화면 출력에 적합한 구조로 변환한다.
    """
    module = str(
        finding.get(
            "module",
            "system",
        )
    )

    error_code = str(
        finding.get(
            "error_code",
            "UNKNOWN_ERROR",
        )
    ).upper()

    original_message = finding.get("message")

    message = (
        str(original_message)
        if original_message
        else get_error_message(error_code)
    )

    metric_name = finding.get("metric_name")
    measured_value = finding.get("measured_value")
    reference_value = finding.get("reference_value")
    tolerance = finding.get("tolerance")
    unit = finding.get("unit")

    measurement_description = (
        build_measurement_description(
            metric_name=(
                str(metric_name)
                if metric_name is not None
                else None
            ),
            measured_value=measured_value,
            reference_value=reference_value,
            tolerance=tolerance,
            unit=(
                str(unit)
                if unit is not None
                else None
            ),
        )
    )

    return {
        "module": module,
        "module_name": get_module_name(module),
        "roi_id": finding.get(
            "roi_id",
            "unknown_roi",
        ),
        "error_code": error_code,
        "message": message,
        "metric_name": metric_name,
        "measured_value": measured_value,
        "reference_value": reference_value,
        "tolerance": tolerance,
        "unit": unit,
        "confidence": finding.get("confidence"),
        "measurement_description": (
            measurement_description
        ),
    }


# =========================================================
# 7. finding 목록 전체 해석
# =========================================================
def interpret_findings(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    findings 목록 전체를 화면 출력용 데이터로 변환한다.
    """
    interpreted_results: list[dict[str, Any]] = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue

        interpreted_results.append(
            interpret_finding(finding)
        )

    return interpreted_results


# =========================================================
# 8. 최종 상태 요약문 생성
# =========================================================
def build_status_summary(
    final_status: str,
    finding_count: int,
) -> str:
    """
    PASS, FAIL, REVIEW 상태에 따른 요약 문장을 만든다.
    """
    normalized_status = str(
        final_status
    ).strip().upper()

    if normalized_status == "PASS":
        return (
            "검사 결과 정상으로 판정되었습니다. "
            "기준을 벗어난 오류 항목이 발견되지 않았습니다."
        )

    if normalized_status == "FAIL":
        return (
            f"검사 결과 불합격으로 판정되었습니다. "
            f"총 {finding_count}개의 오류 항목이 검출되었습니다."
        )

    if normalized_status == "REVIEW":
        return (
            f"검사 결과 추가 검토가 필요합니다. "
            f"총 {finding_count}개의 확인 항목이 존재합니다."
        )

    return (
        "선택한 이미지에 대한 최종 판정 정보를 "
        "확인할 수 없습니다."
    )