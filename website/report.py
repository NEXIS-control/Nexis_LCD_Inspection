"""
website/report.py

모델 단위 판독 결과를 Word(.docx) 리포트로 생성하는 모듈.

구성:
    1. 표지            - 모델명 / 현재 정확도 / 총 판독 횟수 / 출력일시
    2. 판독 이력 요약    - 차수별 표(Capture/PASS/FAIL/정확도)
                          (표지와 같은 첫 페이지에 이어서 출력)
    3. 차수별 상세 결과  - 1차, 2차, 3차... 각각 별도 섹션으로
                          FAIL 상세만 표시 (이미지 + 오류원인 + 상세판독정보)
                          PASS 건은 목록으로 나열하지 않는다
    4. 이전 차수들       - 이미지 없이 차수별 PASS/FAIL 개수 요약만

web.py의 "모델 리포트" 버튼에서 generate_model_report(model_id)를 호출하면
저장된 .docx 파일 경로를 반환한다. web.py는 이 경로를 읽어 st.download_button
으로 사용자에게 다운로드시키면 된다.
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from scenario_model_service import load_model_from_scenarios


# =========================================================
# 0. 프로젝트 경로
# =========================================================

WEBSITE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEBSITE_DIR.parent

ROI_VISUALIZATION_OUTPUT_DIR = (
    PROJECT_ROOT / "roi_visualization" / "output"
)

REPORT_OUTPUT_DIR = PROJECT_ROOT / "web_data" / "reports"


# =========================================================
# 1. 색상 / 스타일 상수
# =========================================================

COLOR_HEADING = RGBColor(0x11, 0x18, 0x27)
COLOR_MUTED = RGBColor(0x6B, 0x72, 0x80)
COLOR_PASS = RGBColor(0x15, 0x80, 0x3D)
COLOR_FAIL = RGBColor(0xB9, 0x1C, 0x1C)
COLOR_TABLE_HEADER_BG = "E9EDF3"

KOREAN_FONT = "맑은 고딕"


def _resolve_korean_font_for_matplotlib() -> str | None:
    """
    matplotlib에서 한글이 깨지지 않도록 시스템에 설치된
    한글 지원 폰트를 찾아 이름을 반환한다.

    우선순위: macOS(AppleGothic) > Windows(맑은 고딕) >
              리눅스(NanumGothic 계열) > 없으면 None.
    """
    candidates = [
        "AppleGothic",
        "Apple SD Gothic Neo",
        "맑은 고딕",
        "Malgun Gothic",
        "NanumGothic",
        "Noto Sans CJK KR",
        "Noto Sans KR",
    ]

    available_names = {font.name for font in font_manager.fontManager.ttflist}

    for name in candidates:
        if name in available_names:
            return name

    return None


_MPL_KOREAN_FONT = _resolve_korean_font_for_matplotlib()

if _MPL_KOREAN_FONT:
    plt.rcParams["font.family"] = _MPL_KOREAN_FONT

plt.rcParams["axes.unicode_minus"] = False


def _chart_text(korean: str, fallback: str) -> str:
    """
    matplotlib이 그리는 차트 안의 텍스트 전용 헬퍼.

    시스템에 한글 폰트가 없으면(예: 한글 미설치 리눅스 서버)
    글자가 네모(tofu)로 깨지는 대신 영문 대체 텍스트를 쓴다.
    docx 표/제목 등 python-docx가 직접 쓰는 텍스트는 이 함수와
    무관하게 항상 한글 그대로 나간다 (Word가 폰트를 자체 처리).
    """
    if _MPL_KOREAN_FONT:
        return korean

    return fallback


def _create_accuracy_chart_image(rounds: list[dict]) -> io.BytesIO:
    """
    차수별 PASS 비율(막대) + 정확도(라인)를 같은 축(0~100%)에
    겹쳐 그리고, 첫 차수 대비 마지막 차수의 상승폭을
    브라켓으로 강조한 차트를 PNG로 만들어 반환한다.
    """
    if _MPL_KOREAN_FONT:
        round_labels = [f"{r.get('round_number', '-')}차" for r in rounds]
    else:
        round_labels = [f"Round {r.get('round_number', '-')}" for r in rounds]

    pass_rates = []
    accuracies = []

    for round_data in rounds:
        capture_count = int(round_data.get("capture_count", 0) or 0)
        pass_count = int(round_data.get("pass_count", 0) or 0)

        pass_rate = (
            (pass_count / capture_count * 100) if capture_count > 0 else 0.0
        )
        pass_rates.append(pass_rate)

        accuracy = round_data.get("accuracy")
        accuracies.append(float(accuracy) if accuracy is not None else pass_rate)

    figure, axis = plt.subplots(figsize=(6.4, 3.4), dpi=170)

    x_positions = range(len(round_labels))

    axis.bar(
        x_positions,
        pass_rates,
        width=0.5,
        color="#1baf7a",
        zorder=2,
        label=_chart_text("PASS 비율", "PASS rate"),
    )

    axis.plot(
        x_positions,
        accuracies,
        color="#2a78d6",
        linewidth=2.6,
        marker="o",
        markersize=8,
        markerfacecolor="#2a78d6",
        markeredgecolor="white",
        markeredgewidth=1.6,
        zorder=3,
        label=_chart_text("정확도", "Accuracy"),
    )

    axis.fill_between(
        x_positions, accuracies, color="#2a78d6", alpha=0.12, zorder=1
    )

    for x, value in zip(x_positions, accuracies):
        axis.annotate(
            f"{value:.1f}%",
            (x, value),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=10,
            color="#0c447c",
            fontweight="medium",
        )

    # ---------------------------------------------------------
    # 첫 차수 대비 마지막 차수 상승폭 브라켓
    # ---------------------------------------------------------

    y_upper_limit = 118

    if len(accuracies) >= 2:
        first_value = accuracies[0]
        last_value = accuracies[-1]
        delta = last_value - first_value

        bracket_y = max(accuracies) + 22
        first_x = x_positions[0]
        last_x = x_positions[-1]

        # 브라켓이 100%에 가까운 값 때문에 축 상단 밖으로
        # 잘리지 않도록, 브라켓 + 라벨 공간을 감안해
        # y축 상한을 데이터에 맞춰 동적으로 넉넉하게 잡는다.
        y_upper_limit = max(118, bracket_y + 18)

        axis.plot(
            [first_x, first_x, last_x, last_x],
            [first_value + 10, bracket_y, bracket_y, last_value + 10],
            color="#3b6d11",
            linewidth=1.3,
            zorder=4,
        )

        delta_text = f"{'+' if delta >= 0 else ''}{delta:.1f}%p"

        axis.annotate(
            delta_text,
            ((first_x + last_x) / 2, bracket_y),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=11,
            color="#3b6d11",
            fontweight="bold",
        )

    axis.set_ylim(0, y_upper_limit)
    axis.set_xticks(list(x_positions))
    axis.set_xticklabels(round_labels, fontsize=10.5, color="#52514e")
    axis.set_yticks([0, 20, 40, 60, 80, 100])
    axis.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"], fontsize=9.5, color="#898781")
    axis.set_ylabel("")

    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.spines["left"].set_visible(False)
    axis.spines["bottom"].set_color("#c3c2b7")

    axis.yaxis.grid(True, color="#e1e0d9", linewidth=0.8, zorder=0)
    axis.set_axisbelow(True)
    axis.tick_params(axis="both", length=0)

    legend = axis.legend(
        loc="lower left",
        bbox_to_anchor=(0, -0.28),
        ncol=2,
        frameon=False,
        fontsize=10,
        handlelength=1.4,
        columnspacing=1.5,
    )

    figure.tight_layout()

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", dpi=170)
    plt.close(figure)

    buffer.seek(0)

    return buffer


# =========================================================
# 2. 표시명 매핑 (web.py와 동일)
# =========================================================

CATEGORY_DISPLAY_NAMES = {
    "text_list": "텍스트 목록",
    "status_time": "상태 · 시간",
    "guide_image": "안내 이미지",
    "popup": "팝업",
    "card_ui": "카드 UI",
    "setting_control": "설정 화면",
    "general_diff": "일반 화면",
}


# =========================================================
# 3. 포맷 헬퍼 (web.py와 동일 로직)
# =========================================================

def format_accuracy(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "-"


def format_decimal(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def format_percentage_from_ratio(value: Any) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
        if 0 <= number <= 1:
            number *= 100
        return f"{number:.2f}%"
    except (TypeError, ValueError):
        return "-"


def get_category_display_name(value: Any) -> str:
    category = str(value or "").strip().lower()
    return CATEGORY_DISPLAY_NAMES.get(category, "일반 화면")


# =========================================================
# 4. 판독 결과 데이터 헬퍼 (web.py와 동일 로직)
# =========================================================

def get_display_file_name(result_key: str, result_data: dict) -> str:
    candidates = [
        result_data.get("file_name"),
        result_data.get("capture_file"),
        result_data.get("screen_id"),
        result_key,
    ]
    for candidate in candidates:
        if candidate:
            return Path(str(candidate)).name
    return "파일명 없음"


def split_results_by_status(
    results_mapping: dict,
) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]]]:
    pass_results = []
    fail_results = []

    for result_key, result_data in results_mapping.items():
        if not isinstance(result_data, dict):
            continue

        status = str(result_data.get("final_status", "")).strip().upper()

        if status == "PASS":
            pass_results.append((str(result_key), result_data))
        elif status == "FAIL":
            fail_results.append((str(result_key), result_data))

    pass_results.sort(key=lambda item: get_display_file_name(*item).lower())
    fail_results.sort(key=lambda item: get_display_file_name(*item).lower())

    return pass_results, fail_results


def get_failure_reasons(result_data: dict) -> list[str]:
    for key in ["final_reasons", "reasons"]:
        reasons = result_data.get(key)
        if isinstance(reasons, list):
            cleaned = [str(r).strip() for r in reasons if str(r).strip()]
            if cleaned:
                return cleaned

    reason = result_data.get("reason")
    if reason:
        return [str(reason).strip()]

    return ["기준 이미지와 차이가 검출되었습니다."]


def clean_failure_reason(reason: str) -> str:
    text = str(reason).strip()

    if not text:
        return "기준 이미지와 차이가 검출되었습니다."

    text = re.sub(r":\s*[A-Za-z_][A-Za-z0-9_]*\s*=.*$", "", text)
    text = re.sub(
        r"\b[A-Za-z_][A-Za-z0-9_]*\s*=\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b",
        "",
        text,
    )

    internal_terms = [
        "area_delta",
        "histogram_distance",
        "diff_ratio",
        "diff_area_ratio",
        "total_diff_area_ratio",
        "overall_ssim",
        "minimum_roi_ssim",
        "min_roi_ssim",
    ]
    for term in internal_terms:
        text = re.sub(rf"\b{re.escape(term)}\b", "", text, flags=re.IGNORECASE)

    text = re.sub(r"\s*,\s*,+", ", ", text)
    text = re.sub(r",\s*$", "", text)
    text = re.sub(r":\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if text.endswith("검출됨"):
        text = text[:-3] + "검출되었습니다."
    elif text.endswith("발생함"):
        text = text[:-3] + "발생했습니다."
    elif not text.endswith("."):
        text += "."

    return text


def extract_detail_metrics(result_data: dict) -> dict[str, Any]:
    """
    상세 판독 정보 표에 쓸 5개 지표를 뽑아낸다.
    (검사 유형 / 차이 영역 / 전체 차이 비율 / 전체 유사도 / 최저 유사도)
    """
    diff_summary = result_data.get("diff_summary", {})
    evidence_summary = result_data.get("evidence_summary", {})

    if not isinstance(diff_summary, dict):
        diff_summary = {}
    if not isinstance(evidence_summary, dict):
        evidence_summary = {}

    diff_roi_count = diff_summary.get("diff_roi_count")
    if diff_roi_count is None:
        diff_roi_count = evidence_summary.get("diff_roi_count")

    total_diff_ratio = diff_summary.get("total_diff_area_ratio")
    if total_diff_ratio is None:
        total_diff_ratio = evidence_summary.get("total_diff_area_ratio")

    overall_ssim = evidence_summary.get("overall_ssim")

    minimum_roi_ssim = evidence_summary.get("minimum_roi_ssim")
    if minimum_roi_ssim is None:
        minimum_roi_ssim = evidence_summary.get("min_roi_ssim")

    return {
        "category": get_category_display_name(result_data.get("category")),
        "diff_roi_count": (
            f"{diff_roi_count}개" if diff_roi_count is not None else "-"
        ),
        "total_diff_ratio": format_percentage_from_ratio(total_diff_ratio),
        "overall_ssim": format_decimal(overall_ssim),
        "minimum_roi_ssim": format_decimal(minimum_roi_ssim),
    }


# =========================================================
# 5. 이미지 경로 탐색 (web.py와 동일 로직)
# =========================================================

def find_image(
    image_dir: Path,
    result_key: str,
    result_data: dict,
    *,
    preferred_field: str | None = None,
) -> Path | None:
    if not image_dir.exists():
        return None

    candidates = []

    if preferred_field:
        candidates.append(result_data.get(preferred_field))

    candidates.extend(
        [
            result_data.get("file_name"),
            result_data.get("capture_file"),
            result_data.get("screen_id"),
            result_key,
        ]
    )

    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".webp"]

    for candidate in candidates:
        if not candidate:
            continue

        candidate_text = str(candidate).strip()
        if not candidate_text:
            continue

        candidate_name = Path(candidate_text).name
        direct_path = image_dir / candidate_name

        if direct_path.exists() and direct_path.is_file():
            return direct_path

        stem = Path(candidate_name).stem

        for extension in supported_extensions:
            possible_path = image_dir / f"{stem}{extension}"
            if possible_path.exists() and possible_path.is_file():
                return possible_path

    return None


def find_reference_image(
    reference_dir: Path, result_key: str, result_data: dict
) -> Path | None:
    return find_image(
        reference_dir,
        result_key,
        result_data,
        preferred_field="reference_image",
    )


def find_capture_image(
    capture_dir: Path, result_key: str, result_data: dict
) -> Path | None:
    return find_image(
        capture_dir,
        result_key,
        result_data,
        preferred_field="capture_file",
    )


def get_roi_visualization_dir(scenario_id: str | None) -> Path | None:
    if not scenario_id:
        return None

    scenario_name = str(scenario_id).strip().lower()

    round_match = re.fullmatch(r"model_([a-z])_round_(\d+)", scenario_name)

    if round_match:
        model_letter = round_match.group(1).upper()
        round_number = int(round_match.group(2))
    else:
        simple_match = re.fullmatch(r"model_([a-z])", scenario_name)
        if not simple_match:
            return None
        model_letter = simple_match.group(1).upper()
        round_number = 1

    roi_dir = ROI_VISUALIZATION_OUTPUT_DIR / f"{model_letter}-{round_number}차"

    if roi_dir.exists() and roi_dir.is_dir():
        return roi_dir

    return None


def find_fail_display_image(
    capture_dir: Path,
    result_key: str,
    result_data: dict,
    *,
    scenario_id: str | None = None,
) -> Path | None:
    roi_dir = get_roi_visualization_dir(scenario_id)

    if roi_dir is not None:
        roi_image = find_image(
            roi_dir, result_key, result_data, preferred_field="capture_file"
        )
        if roi_image is not None:
            return roi_image

    return find_capture_image(capture_dir, result_key, result_data)


# =========================================================
# 6. docx 저수준 헬퍼
# =========================================================

def _setup_document_defaults(document: Document) -> None:
    normal_style = document.styles["Normal"]
    normal_style.font.name = KOREAN_FONT
    normal_style.font.size = Pt(10)

    east_asian_font = normal_style.element.rPr.rFonts
    east_asian_font.set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia",
        KOREAN_FONT,
    )

    sections = document.sections
    for section in sections:
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)
        section.top_margin = Cm(1.8)
        section.bottom_margin = Cm(1.8)


def _add_bottom_border(paragraph, *, color_hex: str, size: int = 8) -> None:
    """
    문단 아래에 강조선(밑줄 형태의 테두리)을 추가한다.
    제목류를 시각적으로 구분 짓는 용도로 쓴다.

    size는 8분의 1pt 단위 (docx 표준). 예: size=12 -> 1.5pt 두께.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph_properties = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")

    bottom_border = OxmlElement("w:bottom")
    bottom_border.set(qn("w:val"), "single")
    bottom_border.set(qn("w:sz"), str(size))
    bottom_border.set(qn("w:space"), "6")
    bottom_border.set(qn("w:color"), color_hex)

    borders.append(bottom_border)
    paragraph_properties.append(borders)


def _shade_paragraph(paragraph, hex_color: str) -> None:
    """문단 전체에 옅은 배경색을 준다 (표 셀 음영과 동일한 방식)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph_properties = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), hex_color)
    paragraph_properties.append(shading)


def _add_kicker(document: Document, text: str) -> None:
    """리포트 맨 위 작은 라벨 (예: 'LCD 자동 합부 판정 리포트')."""
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(10.5)
    run.font.color.rgb = COLOR_MUTED


def _add_title(document: Document, text: str, size: int = 30) -> None:
    """표지의 메인 제목 (모델명 / 차수명). 크고 굵게 + 강조선."""
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(14)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = COLOR_HEADING

    _add_bottom_border(paragraph, color_hex="1BAF7A", size=16)


def _add_section_heading(document: Document, text: str) -> None:
    """섹션 제목 (예: '1. 판독 이력 요약', '2. 1차 판독 상세 결과')."""
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(20)
    paragraph.paragraph_format.space_after = Pt(10)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(17)
    run.font.color.rgb = COLOR_HEADING

    _add_bottom_border(paragraph, color_hex="C3C2B7", size=6)


def _add_sub_heading(document: Document, text: str) -> None:
    """소제목 (예: '정확도 추이', 'FAIL 상세 (N건)')."""
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(12)
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(13.5)
    run.font.color.rgb = COLOR_HEADING


def _add_caption(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.size = Pt(9)
    run.font.color.rgb = COLOR_MUTED


def _shade_cell(cell, hex_color: str) -> None:
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), hex_color)
    cell._tc.get_or_add_tcPr().append(shading)


def _make_table(document: Document, headers: list[str]) -> Any:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    header_cells = table.rows[0].cells
    for index, header_text in enumerate(headers):
        header_cells[index].text = ""
        run = header_cells[index].paragraphs[0].add_run(header_text)
        run.bold = True
        run.font.size = Pt(9.5)
        _shade_cell(header_cells[index], COLOR_TABLE_HEADER_BG)
        header_cells[index].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    return table


def _add_table_row(table, values: list[str], *, center: bool = True) -> None:
    row_cells = table.add_row().cells
    for index, value in enumerate(values):
        row_cells[index].text = ""
        run = row_cells[index].paragraphs[0].add_run(str(value))
        run.font.size = Pt(9.5)
        if center:
            row_cells[index].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER


def _add_status_badge(paragraph, status: str) -> None:
    run = paragraph.add_run(f" [{status}]")
    run.bold = True
    run.font.size = Pt(13)
    run.font.color.rgb = COLOR_PASS if status == "PASS" else COLOR_FAIL


def _add_image_pair(
    document: Document,
    *,
    reference_image: Path | None,
    capture_image: Path | None,
    image_width_cm: float = 7.3,
) -> None:
    table = document.add_table(rows=2, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    label_cells = table.rows[0].cells
    for cell, label in zip(label_cells, ["Reference (정상 기준)", "Capture (오류 위치)"]):
        cell.text = ""
        run = cell.paragraphs[0].add_run(label)
        run.bold = True
        run.font.size = Pt(9.5)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

    image_cells = table.rows[1].cells

    for cell, image_path in zip(image_cells, [reference_image, capture_image]):
        cell.text = ""
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

        if image_path is not None and image_path.exists():
            run = paragraph.add_run()
            run.add_picture(str(image_path), width=Cm(image_width_cm))
        else:
            run = paragraph.add_run("이미지를 찾을 수 없습니다.")
            run.font.size = Pt(9)
            run.font.color.rgb = COLOR_MUTED


# =========================================================
# 7. 리포트 섹션 빌더
# =========================================================

def _build_cover(document: Document, model: dict) -> None:
    model_name = str(model.get("model_name", "Model"))
    accuracy_text = format_accuracy(model.get("latest_accuracy"))
    inspection_count = model.get("inspection_count", 0)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    _add_kicker(document, "LCD 자동 합부 판정 리포트")
    document.add_paragraph()
    _add_title(document, model_name, size=32)

    document.paragraphs[-1].paragraph_format.space_after = Pt(20)

    info_table = _make_table(
        document, ["현재 정확도", "총 판독 횟수", "리포트 생성일시"]
    )
    _add_table_row(
        info_table,
        [accuracy_text, f"{inspection_count}회", generated_at],
    )

    rounds = sorted(
        model.get("rounds", []),
        key=lambda item: int(item.get("round_number", 0)),
    )

    if rounds:
        document.add_paragraph()
        _add_sub_heading(document, "정확도 추이")

        chart_image = _create_accuracy_chart_image(rounds)

        chart_paragraph = document.add_paragraph()
        chart_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        chart_run = chart_paragraph.add_run()
        chart_run.add_picture(chart_image, width=Cm(15))


def _build_round_cover(
    document: Document, *, model_name: str, round_data: dict
) -> None:
    round_number = round_data.get("round_number", "-")
    accuracy_text = format_accuracy(round_data.get("accuracy"))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    _add_kicker(document, "LCD 자동 합부 판정 리포트")
    document.add_paragraph()
    _add_title(document, f"{model_name} · {round_number}차 판독 결과", size=24)

    document.paragraphs[-1].paragraph_format.space_after = Pt(20)

    info_table = _make_table(
        document, ["전체 판독", "PASS", "FAIL", "PASS 비율", "생성일시"]
    )
    _add_table_row(
        info_table,
        [
            f"{round_data.get('capture_count', 0)}개",
            round_data.get("pass_count", 0),
            round_data.get("fail_count", 0),
            accuracy_text,
            generated_at,
        ],
    )

    document.add_paragraph()


def _build_history_summary(document: Document, model: dict) -> None:
    _add_section_heading(document, "1. 판독 이력 요약")

    rounds = sorted(
        model.get("rounds", []),
        key=lambda item: int(item.get("round_number", 0)),
    )

    history_table = _make_table(
        document, ["차수", "Capture 수", "PASS", "FAIL", "정확도"]
    )

    for round_data in rounds:
        _add_table_row(
            history_table,
            [
                f"{round_data.get('round_number', '-')}차",
                f"{round_data.get('capture_count', 0)}개",
                round_data.get("pass_count", 0),
                round_data.get("fail_count", 0),
                format_accuracy(round_data.get("accuracy")),
            ],
        )


def _build_fail_detail(
    document: Document,
    *,
    result_key: str,
    result_data: dict,
    reference_dir: Path,
    capture_dir: Path,
    scenario_id: str,
) -> None:
    display_name = get_display_file_name(result_key, result_data)

    heading_paragraph = document.add_paragraph()
    heading_paragraph.paragraph_format.space_before = Pt(18)
    heading_paragraph.paragraph_format.space_after = Pt(8)
    heading_paragraph.paragraph_format.left_indent = Pt(6)
    _shade_paragraph(heading_paragraph, "FBEAEA")

    heading_run = heading_paragraph.add_run(display_name)
    heading_run.bold = True
    heading_run.font.size = Pt(13.5)
    _add_status_badge(heading_paragraph, "FAIL")

    reference_image = find_reference_image(reference_dir, result_key, result_data)
    capture_image = find_fail_display_image(
        capture_dir, result_key, result_data, scenario_id=scenario_id
    )

    _add_image_pair(
        document,
        reference_image=reference_image,
        capture_image=capture_image,
        image_width_cm=6.6,
    )

    reason_paragraph = document.add_paragraph()
    reason_paragraph.paragraph_format.space_before = Pt(6)
    reason_run = reason_paragraph.add_run("오류 원인")
    reason_run.bold = True
    reason_run.font.size = Pt(10)

    for reason in get_failure_reasons(result_data):
        cleaned_reason = clean_failure_reason(str(reason))
        bullet_paragraph = document.add_paragraph(style="List Bullet")
        bullet_run = bullet_paragraph.add_run(cleaned_reason)
        bullet_run.font.size = Pt(9.5)
        bullet_run.font.color.rgb = COLOR_FAIL

    metrics = extract_detail_metrics(result_data)

    detail_table = _make_table(
        document,
        ["검사 유형", "차이 영역", "전체 차이 비율", "전체 유사도", "최저 유사도"],
    )
    _add_table_row(
        detail_table,
        [
            metrics["category"],
            metrics["diff_roi_count"],
            metrics["total_diff_ratio"],
            metrics["overall_ssim"],
            metrics["minimum_roi_ssim"],
        ],
    )


def _build_round_detail_body(document: Document, round_data: dict) -> None:
    """
    특정 차수(scenario) 하나의 상세 결과를 문서에 그린다.

    - PASS/FAIL 요약 카드
    - FAIL 상세 (Reference/Capture 이미지 + 오류원인 + 상세판독정보)

    PASS 건은 목록으로 나열하지 않는다 — 리포트는 FAIL(오류)
    확인용이므로 요약 카드의 PASS 개수만으로 충분하다.

    모델 리포트의 "최신 차수 상세"와
    차수별 리포트의 본문에서 공통으로 사용한다.
    """
    summary_table = _make_table(
        document, ["전체 판독", "PASS", "FAIL", "PASS 비율"]
    )
    _add_table_row(
        summary_table,
        [
            f"{round_data.get('capture_count', 0)}개",
            round_data.get("pass_count", 0),
            round_data.get("fail_count", 0),
            format_accuracy(round_data.get("accuracy")),
        ],
    )

    results_mapping = round_data.get("results_mapping", {})
    _, fail_results = split_results_by_status(results_mapping)

    reference_dir = Path(round_data.get("reference_dir") or ".")
    capture_dir = Path(round_data.get("capture_dir") or ".")
    scenario_id = str(round_data.get("scenario_id", ""))

    document.add_paragraph()
    _add_sub_heading(document, f"FAIL 상세 ({len(fail_results)}건)")

    if not fail_results:
        _add_caption(document, "FAIL 판독 결과가 없습니다.")
    else:
        for result_key, result_data in fail_results:
            _build_fail_detail(
                document,
                result_key=result_key,
                result_data=result_data,
                reference_dir=reference_dir,
                capture_dir=capture_dir,
                scenario_id=scenario_id,
            )


def _build_all_rounds_detail(document: Document, model: dict) -> None:
    """
    모델의 모든 차수(1차, 2차, 3차...)를 각각 별도 섹션으로 나눠
    FAIL 상세(이미지 포함)를 전부 상세하게 담는다.

    "최신 차수만 상세, 이전 차수는 개수만" 구조가 아니라
    모든 차수를 동일하게 상세히 다룬다.
    """
    rounds = sorted(
        model.get("rounds", []),
        key=lambda item: int(item.get("round_number", 0)),
    )

    if not rounds:
        return

    for index, round_data in enumerate(rounds):
        round_number = round_data.get("round_number", "-")

        if index > 0:
            document.add_page_break()

        _add_section_heading(
            document, f"{index + 2}. {round_number}차 판독 상세 결과"
        )

        _build_round_detail_body(document, round_data)


# =========================================================
# 8. 메인 엔트리 포인트
# =========================================================

def generate_model_report(model_id: str) -> Path:
    """
    지정한 model_id의 판독 결과를 Word(.docx) 리포트로 생성하고
    저장된 파일 경로를 반환한다.

    web.py에서 사용 예:

        from report import generate_model_report

        report_path = generate_model_report(model_id)

        with open(report_path, "rb") as file:
            st.download_button(
                "리포트 다운로드",
                data=file.read(),
                file_name=report_path.name,
                mime=(
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
            )
    """
    model = load_model_from_scenarios(model_id)

    if not model:
        raise ValueError(f"모델 정보를 찾을 수 없습니다: {model_id}")

    if not model.get("rounds"):
        raise ValueError(f"판독 이력이 없는 모델입니다: {model_id}")

    document = Document()
    _setup_document_defaults(document)

    _build_cover(document, model)
    _build_history_summary(document, model)
    document.add_page_break()
    _build_all_rounds_detail(document, model)

    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = REPORT_OUTPUT_DIR / f"{model_id}_report_{timestamp}.docx"

    document.save(output_path)

    return output_path


def generate_round_report(model_id: str, scenario_id: str) -> Path:
    """
    특정 차수(scenario_id) 하나의 판독 결과만 담은
    Word(.docx) 리포트를 생성하고 저장된 파일 경로를 반환한다.

    모델 A의 1차, 2차, 3차 결과가 서로 다르므로
    "모델 리포트"(모델 전체 요약)와 별개로,
    판독 결과 화면(inspection_result)에서
    해당 차수만의 리포트를 받을 때 사용한다.

    web.py에서 사용 예:

        from report import generate_round_report

        report_path = generate_round_report(model_id, scenario_id)

        with open(report_path, "rb") as file:
            st.download_button(
                "이 차수 리포트 다운로드",
                data=file.read(),
                file_name=report_path.name,
                mime=(
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
            )
    """
    model = load_model_from_scenarios(model_id)

    if not model:
        raise ValueError(f"모델 정보를 찾을 수 없습니다: {model_id}")

    round_data = None
    for candidate in model.get("rounds", []):
        if str(candidate.get("scenario_id", "")) == str(scenario_id):
            round_data = candidate
            break

    if round_data is None:
        raise ValueError(
            f"해당 차수를 찾을 수 없습니다: {model_id} / {scenario_id}"
        )

    model_name = str(model.get("model_name", model_id))

    document = Document()
    _setup_document_defaults(document)

    _build_round_cover(document, model_name=model_name, round_data=round_data)
    _build_round_detail_body(document, round_data)

    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    round_number = round_data.get("round_number", "0")
    output_path = (
        REPORT_OUTPUT_DIR
        / f"{model_id}_{round_number}차_report_{timestamp}.docx"
    )

    document.save(output_path)

    return output_path


# =========================================================
# 9. 실행 테스트
# =========================================================

if __name__ == "__main__":
    import sys

    target_model_id = sys.argv[1] if len(sys.argv) > 1 else "model_a"

    saved_path = generate_model_report(target_model_id)

    print(f"리포트 생성 완료: {saved_path}")