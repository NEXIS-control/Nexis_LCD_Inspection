from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance
import streamlit as st

from result_interpreter import (
    build_status_summary,
    interpret_findings,
)


# =========================================================
# 1. Streamlit 기본 설정
# =========================================================
st.set_page_config(
    page_title="NEXIS LCD Inspection",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# 2. 사용자 CSS
# =========================================================
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    .main-title {
        font-size: 2.1rem;
        font-weight: 800;
        margin-bottom: 0.15rem;
        color: #1f2937;
    }

    .sub-title {
        font-size: 0.95rem;
        color: #6b7280;
        margin-bottom: 1.5rem;
    }

    .section-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1f2937;
        margin-top: 0.5rem;
        margin-bottom: 0.8rem;
    }

    .status-card {
        border-radius: 16px;
        padding: 1.4rem 1.6rem;
        text-align: center;
        font-weight: 800;
        font-size: 2rem;
        margin-bottom: 1rem;
        border: 1px solid rgba(0, 0, 0, 0.08);
    }

    .status-pass {
        background-color: rgba(34, 197, 94, 0.12);
        color: #15803d;
    }

    .status-fail {
        background-color: rgba(239, 68, 68, 0.12);
        color: #b91c1c;
    }

    .status-review {
        background-color: rgba(245, 158, 11, 0.15);
        color: #b45309;
    }

    .status-unknown {
        background-color: rgba(107, 114, 128, 0.12);
        color: #4b5563;
    }

    .summary-box {
        background-color: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 1rem;
    }

    .file-box {
        background-color: #f8fafc;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 0.8rem 1rem;
        min-height: 92px;
    }

    .image-caption {
        font-size: 0.86rem;
        color: #6b7280;
        margin-top: 0.35rem;
        word-break: break-all;
    }

    .issue-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-left: 5px solid #9ca3af;
        border-radius: 12px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.8rem;
    }

    .issue-title {
        font-size: 1rem;
        font-weight: 700;
        color: #111827;
        margin-bottom: 0.4rem;
    }

    .issue-description {
        color: #374151;
        margin-bottom: 0.6rem;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        padding: 1rem;
        border-radius: 14px;
    }

    div[data-testid="stMetricLabel"] {
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 3. 프로젝트 경로
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
CAPTURE_DIR = PROJECT_ROOT / "data" / "capture"

ANALYSIS_RESULT_PATH = (
    PROJECT_ROOT
    / "sample_data"
    / "sample_analysis_result.json"
)

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
}


# =========================================================
# 4. 이미지 검색
# =========================================================
def find_image_files(folder: Path) -> list[Path]:
    """
    폴더 내부에서 지원되는 이미지 파일을 검색한다.
    """
    if not folder.exists():
        return []

    image_files = [
        path
        for path in folder.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    return sorted(
        image_files,
        key=lambda path: path.name.lower(),
    )


# =========================================================
# 5. 이미지 ID 매핑
# =========================================================
def build_image_map(
    image_files: list[Path],
) -> dict[str, Path]:
    """
    확장자를 제외한 파일명을 이미지 ID로 사용한다.

    예:
        11-10.png -> 11-10
    """
    return {
        image_path.stem: image_path
        for image_path in image_files
    }


# =========================================================
# 6. JSON 파일 읽기
# =========================================================
def load_json(path: Path) -> dict[str, Any]:
    """
    JSON 파일을 읽어 딕셔너리로 반환한다.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"분석 결과 JSON 파일이 없습니다: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "JSON 최상위 구조는 객체 형식이어야 합니다."
        )

    return data


# =========================================================
# 7. 분석 결과 검색
# =========================================================
def find_analysis_result(
    analysis_data: dict[str, Any],
    selected_id: str,
) -> dict[str, Any] | None:
    """
    JSON의 results 목록에서 pair_id가 같은 결과를 찾는다.
    """
    results = analysis_data.get("results", [])

    if not isinstance(results, list):
        raise ValueError(
            "JSON의 'results' 항목은 리스트 형식이어야 합니다."
        )

    for result in results:
        if not isinstance(result, dict):
            continue

        pair_id = str(
            result.get("pair_id", "")
        )

        if pair_id == selected_id:
            return result

    return None


# =========================================================
# 8. 이미지 안전하게 열기
# =========================================================
def open_image(path: Path) -> Image.Image:
    """
    이미지 파일을 RGB 형식으로 열어 반환한다.
    """
    image = Image.open(path)

    return image.convert("RGB")


# =========================================================
# 9. Difference 이미지 생성
# =========================================================
def create_difference_image(
    reference_path: Path,
    capture_path: Path,
    enhancement_factor: float = 3.0,
) -> Image.Image:
    """
    Reference와 Capture 이미지의 차이 이미지를 생성한다.

    두 이미지 크기가 다르면 Capture 이미지를
    Reference 이미지 크기에 맞춰 조정한다.
    """
    reference_image = open_image(reference_path)
    capture_image = open_image(capture_path)

    if capture_image.size != reference_image.size:
        capture_image = capture_image.resize(
            reference_image.size
        )

    difference_image = ImageChops.difference(
        reference_image,
        capture_image,
    )

    enhancer = ImageEnhance.Contrast(
        difference_image
    )

    enhanced_difference = enhancer.enhance(
        enhancement_factor
    )

    return enhanced_difference


# =========================================================
# 10. 상태 표시용 클래스
# =========================================================
def get_status_class(status: str) -> str:
    """
    판정 상태에 맞는 CSS 클래스를 반환한다.
    """
    normalized_status = status.upper()

    if normalized_status == "PASS":
        return "status-pass"

    if normalized_status == "FAIL":
        return "status-fail"

    if normalized_status == "REVIEW":
        return "status-review"

    return "status-unknown"


# =========================================================
# 11. 상태 카드 출력
# =========================================================
def display_status_card(
    status: str,
    pair_id: str,
) -> None:
    """
    PASS / FAIL / REVIEW 판정 카드를 출력한다.
    """
    normalized_status = status.upper()
    status_class = get_status_class(
        normalized_status
    )

    status_icon = {
        "PASS": "✅",
        "FAIL": "❌",
        "REVIEW": "⚠️",
    }.get(
        normalized_status,
        "❔",
    )

    st.markdown(
        f"""
        <div class="status-card {status_class}">
            {status_icon} {normalized_status}
            <div style="
                font-size: 0.95rem;
                font-weight: 500;
                margin-top: 0.35rem;
            ">
                Inspection ID: {pair_id}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 12. 분석 원인 표시
# =========================================================
def display_findings(
    findings: list[dict[str, Any]],
    final_status: str,
) -> None:
    """
    result_interpreter.py에서 해석한 결과를 표시한다.
    """
    interpreted_findings = interpret_findings(
        findings
    )

    summary = build_status_summary(
        final_status=final_status,
        finding_count=len(interpreted_findings),
    )

    st.markdown(
        '<div class="section-title">판정 원인</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="summary-box">
            {summary}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not interpreted_findings:
        if final_status.upper() == "PASS":
            st.success(
                "검출된 오류 또는 검토 항목이 없습니다."
            )
        else:
            st.warning(
                "최종 판정은 존재하지만 "
                "세부 원인 데이터가 없습니다."
            )

        return

    for index, finding in enumerate(
        interpreted_findings,
        start=1,
    ):
        error_code = finding.get(
            "error_code",
            "UNKNOWN_ERROR",
        )

        module_name = finding.get(
            "module_name",
            "알 수 없는 검사",
        )

        roi_id = finding.get(
            "roi_id",
            "unknown_roi",
        )

        message = finding.get(
            "message",
            "상세 설명이 없습니다.",
        )

        measurement_description = finding.get(
            "measurement_description",
            "측정값 정보가 없습니다.",
        )

        confidence = finding.get(
            "confidence"
        )

        if isinstance(
            confidence,
            (int, float),
        ):
            confidence_text = (
                f"{confidence * 100:.1f}%"
            )
        else:
            confidence_text = "-"

        with st.expander(
            f"{index}. {module_name} — {error_code}",
            expanded=True,
        ):
            st.markdown(
                f"""
                <div class="issue-card">
                    <div class="issue-title">
                        {module_name}
                    </div>

                    <div class="issue-description">
                        {message}
                    </div>

                    <div>
                        <b>측정 결과:</b>
                        {measurement_description}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            detail_col1, detail_col2 = st.columns(2)

            with detail_col1:
                st.write(
                    f"**검사 영역:** {roi_id}"
                )

                st.write(
                    f"**측정 지표:** "
                    f"{finding.get('metric_name') or '-'}"
                )

                st.write(
                    f"**분석 신뢰도:** "
                    f"{confidence_text}"
                )

            with detail_col2:
                st.write(
                    f"**측정값:** "
                    f"{finding.get('measured_value', '-')}"
                )

                st.write(
                    f"**기준값:** "
                    f"{finding.get('reference_value', '-')}"
                )

                st.write(
                    f"**허용 기준:** "
                    f"{finding.get('tolerance', '-')}"
                )

                st.write(
                    f"**단위:** "
                    f"{finding.get('unit') or '-'}"
                )


# =========================================================
# 13. 이미지와 매칭 정보 준비
# =========================================================
reference_files = find_image_files(
    REFERENCE_DIR
)

capture_files = find_image_files(
    CAPTURE_DIR
)

reference_map = build_image_map(
    reference_files
)

capture_map = build_image_map(
    capture_files
)

common_ids = sorted(
    set(reference_map.keys())
    & set(capture_map.keys()),
    key=str.lower,
)

reference_only_ids = sorted(
    set(reference_map.keys())
    - set(capture_map.keys()),
    key=str.lower,
)

capture_only_ids = sorted(
    set(capture_map.keys())
    - set(reference_map.keys()),
    key=str.lower,
)


# =========================================================
# 14. 폴더 및 파일 검사
# =========================================================
if not REFERENCE_DIR.exists():
    st.error(
        f"Reference 폴더가 없습니다: {REFERENCE_DIR}"
    )
    st.stop()

if not CAPTURE_DIR.exists():
    st.error(
        f"Capture 폴더가 없습니다: {CAPTURE_DIR}"
    )
    st.stop()

if not reference_files:
    st.error(
        "data/reference 폴더에서 "
        "Reference 이미지를 찾지 못했습니다."
    )
    st.stop()

if not capture_files:
    st.error(
        "data/capture 폴더에서 "
        "Capture 이미지를 찾지 못했습니다."
    )
    st.stop()

if not common_ids:
    st.error(
        "Reference와 Capture 폴더에서 "
        "동일한 파일명을 찾지 못했습니다."
    )
    st.stop()


# =========================================================
# 15. 분석 JSON 읽기
# =========================================================
try:
    analysis_data = load_json(
        ANALYSIS_RESULT_PATH
    )

except FileNotFoundError as error:
    st.error(str(error))
    st.stop()

except json.JSONDecodeError as error:
    st.error(
        "분석 결과 JSON 문법에 오류가 있습니다."
    )
    st.code(str(error))
    st.stop()

except ValueError as error:
    st.error(str(error))
    st.stop()


# =========================================================
# 16. 사이드바
# =========================================================
with st.sidebar:
    st.header("Inspection Control")

    selected_id = st.selectbox(
        "비교할 이미지 ID",
        options=common_ids,
        index=0,
    )

    st.divider()

    st.subheader("Dataset Summary")

    st.metric(
        "Reference",
        len(reference_files),
    )

    st.metric(
        "Capture",
        len(capture_files),
    )

    st.metric(
        "Matched Pairs",
        len(common_ids),
    )

    unmatched_count = (
        len(reference_only_ids)
        + len(capture_only_ids)
    )

    st.metric(
        "Unmatched",
        unmatched_count,
    )

    st.divider()

    with st.expander(
        "매칭되지 않은 파일",
        expanded=False,
    ):
        if not reference_only_ids \
                and not capture_only_ids:
            st.success(
                "모든 이미지가 정상적으로 매칭되었습니다."
            )

        if reference_only_ids:
            st.warning(
                "Reference에만 존재하는 ID"
            )
            st.write(reference_only_ids)

        if capture_only_ids:
            st.warning(
                "Capture에만 존재하는 ID"
            )
            st.write(capture_only_ids)


# =========================================================
# 17. 선택된 이미지 경로
# =========================================================
reference_path = reference_map[
    selected_id
]

capture_path = capture_map[
    selected_id
]


# =========================================================
# 18. 선택된 분석 결과
# =========================================================
selected_result = find_analysis_result(
    analysis_data,
    selected_id,
)


# =========================================================
# 19. 상단 제목
# =========================================================
st.markdown(
    """
    <div class="main-title">
        NEXIS LCD Inspection System
    </div>

    <div class="sub-title">
        Reference 이미지와 Capture 이미지를 비교하고,
        분석 결과를 판정·해석하는 LCD 자동 검사 대시보드
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 20. 상단 데이터 요약
# =========================================================
top_col1, top_col2, top_col3, top_col4 = st.columns(4)

top_col1.metric(
    "현재 검사 ID",
    selected_id,
)

top_col2.metric(
    "정상 매칭 쌍",
    len(common_ids),
)

top_col3.metric(
    "Reference 파일",
    len(reference_files),
)

top_col4.metric(
    "Capture 파일",
    len(capture_files),
)


# =========================================================
# 21. 이미지 비교 화면
# =========================================================
st.markdown(
    '<div class="section-title">Image Comparison</div>',
    unsafe_allow_html=True,
)

reference_col, capture_col, difference_col = st.columns(3)

with reference_col:
    st.markdown("### Reference")

    st.image(
        str(reference_path),
        use_container_width=True,
    )

    st.markdown(
        f"""
        <div class="image-caption">
            {reference_path.name}
        </div>
        """,
        unsafe_allow_html=True,
    )

with capture_col:
    st.markdown("### Capture")

    st.image(
        str(capture_path),
        use_container_width=True,
    )

    st.markdown(
        f"""
        <div class="image-caption">
            {capture_path.name}
        </div>
        """,
        unsafe_allow_html=True,
    )

with difference_col:
    st.markdown("### Difference")

    try:
        difference_image = create_difference_image(
            reference_path,
            capture_path,
        )

        st.image(
            difference_image,
            use_container_width=True,
        )

        st.markdown(
            """
            <div class="image-caption">
                Reference와 Capture의 픽셀 차이를
                강조한 이미지
            </div>
            """,
            unsafe_allow_html=True,
        )

    except Exception as error:
        st.error(
            "Difference 이미지를 생성하지 못했습니다."
        )
        st.code(str(error))


# =========================================================
# 22. 파일 정보
# =========================================================
file_info_col1, file_info_col2 = st.columns(2)

with file_info_col1:
    st.markdown(
        f"""
        <div class="file-box">
            <b>Reference File</b><br>
            {reference_path.name}<br>
            <span style="color:#6b7280;">
                {reference_path.parent}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with file_info_col2:
    st.markdown(
        f"""
        <div class="file-box">
            <b>Capture File</b><br>
            {capture_path.name}<br>
            <span style="color:#6b7280;">
                {capture_path.parent}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 23. 분석 결과 화면
# =========================================================
st.divider()

st.markdown(
    '<div class="section-title">Inspection Result</div>',
    unsafe_allow_html=True,
)

if selected_result is None:
    display_status_card(
        status="UNKNOWN",
        pair_id=selected_id,
    )

    st.info(
        f"{selected_id}에 대한 분석 결과가 없습니다."
    )

    st.caption(
        "sample_analysis_result.json의 results 목록에 "
        f'pair_id가 "{selected_id}"인 데이터를 추가하면 '
        "결과가 표시됩니다."
    )

else:
    final_status = str(
        selected_result.get(
            "final_status",
            "UNKNOWN",
        )
    ).upper()

    quality_score = selected_result.get(
        "quality_score"
    )

    processing_time = selected_result.get(
        "processing_time_sec"
    )

    findings = selected_result.get(
        "findings",
        [],
    )

    if not isinstance(findings, list):
        findings = []

    display_status_card(
        status=final_status,
        pair_id=selected_id,
    )

    metric_col1, metric_col2, metric_col3, metric_col4 = (
        st.columns(4)
    )

    metric_col1.metric(
        "최종 판정",
        final_status,
    )

    metric_col2.metric(
        "품질 점수",
        (
            f"{quality_score:.1f}"
            if isinstance(
                quality_score,
                (int, float),
            )
            else "-"
        ),
    )

    metric_col3.metric(
        "처리 시간",
        (
            f"{processing_time:.2f} sec"
            if isinstance(
                processing_time,
                (int, float),
            )
            else "-"
        ),
    )

    metric_col4.metric(
        "검출 항목",
        len(findings),
    )

    st.divider()

    display_findings(
        findings=findings,
        final_status=final_status,
    )


# =========================================================
# 24. 원본 JSON 확인
# =========================================================
st.divider()

with st.expander(
    "현재 분석 결과의 원본 JSON 보기",
    expanded=False,
):
    if selected_result is None:
        st.write(
            "선택한 ID에 해당하는 분석 결과가 없습니다."
        )
    else:
        st.json(
            selected_result
        )


# =========================================================
# 25. 시스템 정보
# =========================================================
with st.expander(
    "시스템 경로 및 설정 정보",
    expanded=False,
):
    st.write(
        f"**Project Root:** `{PROJECT_ROOT}`"
    )

    st.write(
        f"**Reference Directory:** `{REFERENCE_DIR}`"
    )

    st.write(
        f"**Capture Directory:** `{CAPTURE_DIR}`"
    )

    st.write(
        f"**Analysis JSON:** `{ANALYSIS_RESULT_PATH}`"
    )

    st.write(
        "**지원 이미지 형식:** "
        + ", ".join(
            sorted(SUPPORTED_EXTENSIONS)
        )
    )
    