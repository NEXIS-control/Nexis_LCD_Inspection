from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import streamlit as st


# =========================================================
# 0. 프로젝트 경로
# =========================================================

WEBSITE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEBSITE_DIR.parent

CONFIG_DIR = (
    PROJECT_ROOT
    / "config"
)

INSPECTION_PROFILES_PATH = (
    CONFIG_DIR
    / "inspection_profiles.json"
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

if str(WEBSITE_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(WEBSITE_DIR),
    )


# =========================================================
# 1. 판독 결과 조회 서비스
# =========================================================

from scenario_model_service import (
    load_models_from_scenarios,
    load_model_from_scenarios,
    load_scenario_by_id,
)


# =========================================================
# 2. 기존 판독 엔진 Scenario 관리 기능
# =========================================================

from modules.scenario_manager import (
    capture_dir as scenario_capture_dir,
    copy_images,
    create_scenario,
    image_names,
    reference_dir as scenario_reference_dir,
    run_module_for_scenario,
    scenario_data_dir,
    scenario_results_dir,
)


# =========================================================
# 3. Streamlit 기본 설정
# =========================================================

st.set_page_config(
    page_title="NEXIS LCD Inspection System",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# 4. 전체 화면 스타일
# =========================================================

st.markdown(
    """
    <style>

    .stApp {
        background-color: #f3f6fa;
    }

    .block-container {
        max-width: 1250px;
        padding-top: 1.8rem;
        padding-bottom: 3rem;
    }

    div.stButton > button {
        border-radius: 9px;
        font-weight: 650;
        min-height: 2.7rem;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #edf0f4;
        border-radius: 12px;
        padding: 1rem;
    }

    div[data-testid="stMetricLabel"] {
        color: #6b7280;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff;
        border-radius: 16px;
    }

    h1,
    h2,
    h3 {
        color: #111827;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 5. Session State 초기화
# =========================================================

def initialize_session_state() -> None:

    defaults = {
        "current_view": "home",
        "selected_model_id": None,
        "selected_inspection_id": None,
        "selected_file_name": None,
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


# =========================================================
# 6. 기본 공통 함수
# =========================================================

def format_accuracy(
    value,
) -> str:

    if value is None:
        return "-"

    try:
        return f"{float(value):.1f}%"

    except (
        TypeError,
        ValueError,
    ):
        return "-"


def format_decimal(
    value,
    digits: int = 3,
) -> str:

    if value is None:
        return "-"

    try:
        return f"{float(value):.{digits}f}"

    except (
        TypeError,
        ValueError,
    ):
        return "-"


def format_percentage_from_ratio(
    value,
) -> str:

    if value is None:
        return "-"

    try:

        number = float(value)

        if 0 <= number <= 1:
            number *= 100

        return f"{number:.2f}%"

    except (
        TypeError,
        ValueError,
    ):
        return "-"


def go_to_view(
    view_name: str,
    *,
    model_id: str | None = None,
    inspection_id: str | None = None,
    file_name: str | None = None,
) -> None:

    st.session_state.current_view = (
        view_name
    )

    if model_id is not None:

        st.session_state.selected_model_id = (
            model_id
        )

    if inspection_id is not None:

        st.session_state.selected_inspection_id = (
            inspection_id
        )

    if file_name is not None:

        st.session_state.selected_file_name = (
            file_name
        )

    st.rerun()


# =========================================================
# 7. JSON 공통 함수
# =========================================================

def load_json_file(
    path: Path,
) -> dict:

    if not path.exists():
        return {}

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except (
        OSError,
        json.JSONDecodeError,
    ):
        pass

    return {}


def save_json_file(
    path: Path,
    data: dict,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 8. 판독 프로파일 설정
# =========================================================

def load_inspection_profiles() -> dict:
    """
    config/inspection_profiles.json을 읽는다.

    원본 설정은 웹에서 수정하지 않는다.
    """

    return load_json_file(
        INSPECTION_PROFILES_PATH
    )


PROFILE_DISPLAY_NAMES = {

    "general_diff_profile":
        "일반 화면",

    "text_list_profile":
        "텍스트 목록",

    "status_time_profile":
        "시간 · 상태 표시",

    "guide_image_profile":
        "안내 이미지",

    "popup_profile":
        "팝업 화면",

    "card_ui_profile":
        "카드 UI",

    "setting_control_profile":
        "설정 · 제어 화면",
}


PROFILE_HELP_TEXT = {

    "general_diff_profile":
        "특정 유형에 속하지 않는 일반적인 LCD 화면",

    "text_list_profile":
        "목록, 설정 항목, 여러 줄 텍스트가 많은 화면",

    "status_time_profile":
        "시간, 숫자, 진행 상태, 단위 표시가 중요한 화면",

    "guide_image_profile":
        "안내 그림, 설명 이미지, 도식이 포함된 화면",

    "popup_profile":
        "확인·취소·로딩 등 중앙 팝업이 포함된 화면",

    "card_ui_profile":
        "코스 카드, 대시보드, 타일 형태의 UI 화면",

    "setting_control_profile":
        "슬라이더, 토글, 옵션 버튼, 설정값 조절 화면",
}


CHECK_DISPLAY_NAMES = {

    "text_content":
        "텍스트 내용",

    "text_spacing":
        "텍스트 간격",

    "gradient_color":
        "색상 및 그라데이션",

    "text_brightness":
        "텍스트 밝기",

    "progress_bar":
        "진행 상태 표시",

    "image_structure":
        "화면 구성 및 이미지 구조",
}


CHECK_HELP_TEXT = {

    "text_content":
        "표시된 글자의 내용이 기준 화면과 일치하는지 확인합니다.",

    "text_spacing":
        "글자 사이 간격과 텍스트 배치 차이를 확인합니다.",

    "gradient_color":
        "UI 색상과 부드러운 그라데이션의 차이를 확인합니다.",

    "text_brightness":
        "텍스트 밝기가 기준보다 어둡거나 밝은지 확인합니다.",

    "progress_bar":
        "진행바와 상태 표시 영역이 기준과 일치하는지 확인합니다.",

    "image_structure":
        "아이콘, 카드, 이미지 등 화면 구성 요소의 누락·변형을 확인합니다.",
}


def get_default_enabled_checks() -> dict[
    str,
    bool
]:
    """
    inspection_profiles.json의
    binary_policy.enabled_checks를 기본값으로 사용한다.
    """

    config = (
        load_inspection_profiles()
    )

    enabled_checks = (
        config
        .get(
            "binary_policy",
            {},
        )
        .get(
            "enabled_checks",
            {},
        )
    )

    defaults = {}

    for check_key in (
        CHECK_DISPLAY_NAMES
    ):

        defaults[
            check_key
        ] = bool(
            enabled_checks.get(
                check_key,
                True,
            )
        )

    return defaults


# =========================================================
# 9. 새 모델 ID 자동 결정
# =========================================================

def get_next_model_info() -> dict:
    """
    현재 모델 목록을 확인해서
    다음 알파벳 모델을 자동 배정한다.

    예:
    Model A + Model B
    -> Model C
    """

    models = (
        load_models_from_scenarios()
    )

    used_letters = set()

    for model in models:

        model_id = str(
            model.get(
                "model_id",
                "",
            )
        ).lower()

        match = re.fullmatch(
            r"model_([a-z])",
            model_id,
        )

        if match:

            used_letters.add(
                match.group(1)
            )

    next_letter = None

    for letter_code in range(
        ord("a"),
        ord("z") + 1,
    ):

        letter = chr(
            letter_code
        )

        if letter not in (
            used_letters
        ):

            next_letter = (
                letter
            )

            break

    if next_letter is None:

        raise RuntimeError(
            "추가할 수 있는 모델 이름이 없습니다."
        )

    return {
        "model_id":
            f"model_{next_letter}",

        "model_name":
            f"Model {next_letter.upper()}",

        "scenario_id":
            f"model_{next_letter}_round_1",

        "round_number":
            1,
    }


# =========================================================
# 10. 모델별 판독 설정 저장
# =========================================================

def save_scenario_inspection_settings(
    scenario_id: str,
    *,
    model_name: str,
    model_description: str,
    profile_key: str,
    enabled_checks: dict[
        str,
        bool
    ],
) -> None:
    """
    새 모델에서 사용자가 선택한 판독 설정을
    해당 scenario.json에 저장한다.

    원본 inspection_profiles.json은 수정하지 않는다.
    """

    scenario_dir = (
        scenario_data_dir(
            scenario_id
        )
    )

    scenario_json_path = (
        scenario_dir
        / "scenario.json"
    )

    scenario_data = (
        load_json_file(
            scenario_json_path
        )
    )

    scenario_data[
        "model_name"
    ] = model_name

    scenario_data[
        "model_description"
    ] = (
        model_description
    )

    scenario_data[
        "inspection_profile"
    ] = profile_key

    scenario_data[
        "inspection_profile_name"
    ] = (
        PROFILE_DISPLAY_NAMES.get(
            profile_key,
            profile_key,
        )
    )

    scenario_data[
        "enabled_checks"
    ] = enabled_checks

    save_json_file(
        scenario_json_path,
        scenario_data,
    )


# =========================================================
# 11. 판독 결과 공통 함수
# =========================================================

def get_round_number(
    model: dict | None,
    scenario_id: str | None,
) -> int | None:

    if not model:
        return None

    if not scenario_id:
        return None

    for round_data in model.get(
        "rounds",
        [],
    ):

        current_id = str(
            round_data.get(
                "scenario_id",
                "",
            )
        )

        if current_id == str(
            scenario_id
        ):

            try:

                return int(
                    round_data.get(
                        "round_number"
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                return None

    return None


def get_display_file_name(
    result_key: str,
    result_data: dict,
) -> str:

    candidates = [
        result_data.get(
            "file_name"
        ),
        result_data.get(
            "capture_file"
        ),
        result_data.get(
            "screen_id"
        ),
        result_key,
    ]

    for candidate in candidates:

        if candidate:

            return Path(
                str(candidate)
            ).name

    return "파일명 없음"


def split_results_by_status(
    results_mapping: dict,
) -> tuple[
    list[tuple[str, dict]],
    list[tuple[str, dict]],
]:

    pass_results = []
    fail_results = []

    for result_key, result_data in (
        results_mapping.items()
    ):

        if not isinstance(
            result_data,
            dict,
        ):
            continue

        status = str(
            result_data.get(
                "final_status",
                "",
            )
        ).strip().upper()

        if status == "PASS":

            pass_results.append(
                (
                    str(result_key),
                    result_data,
                )
            )

        elif status == "FAIL":

            fail_results.append(
                (
                    str(result_key),
                    result_data,
                )
            )

    pass_results.sort(
        key=lambda item:
        get_display_file_name(
            item[0],
            item[1],
        ).lower()
    )

    fail_results.sort(
        key=lambda item:
        get_display_file_name(
            item[0],
            item[1],
        ).lower()
    )

    return (
        pass_results,
        fail_results,
    )


# =========================================================
# 12. 이미지 검색
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

        candidates.append(
            result_data.get(
                preferred_field
            )
        )

    candidates.extend(
        [
            result_data.get(
                "file_name"
            ),
            result_data.get(
                "capture_file"
            ),
            result_data.get(
                "screen_id"
            ),
            result_key,
        ]
    )

    supported_extensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".webp",
    ]

    for candidate in candidates:

        if not candidate:
            continue

        candidate_text = str(
            candidate
        ).strip()

        if not candidate_text:
            continue

        candidate_name = Path(
            candidate_text
        ).name

        direct_path = (
            image_dir
            / candidate_name
        )

        if (
            direct_path.exists()
            and direct_path.is_file()
        ):

            return direct_path

        stem = Path(
            candidate_name
        ).stem

        for extension in (
            supported_extensions
        ):

            possible_path = (
                image_dir
                / f"{stem}{extension}"
            )

            if (
                possible_path.exists()
                and possible_path.is_file()
            ):

                return possible_path

    return None


def find_capture_image(
    capture_dir: Path,
    result_key: str,
    result_data: dict,
) -> Path | None:

    return find_image(
        capture_dir,
        result_key,
        result_data,
        preferred_field="capture_file",
    )


def find_reference_image(
    reference_dir: Path,
    result_key: str,
    result_data: dict,
) -> Path | None:

    return find_image(
        reference_dir,
        result_key,
        result_data,
        preferred_field="reference_image",
    )


# =========================================================
# 13. FAIL 표시 이미지
# =========================================================

def find_fail_display_image(
    capture_dir: Path,
    result_key: str,
    result_data: dict,
) -> Path | None:
    """
    현재 FAIL 화면에서는 원본 Capture 이미지를 표시한다.

    오류 위치 표시 이미지가 완성되면
    이 함수만 수정하면 된다.
    """

    return find_capture_image(
        capture_dir,
        result_key,
        result_data,
    )


# =========================================================
# 14. FAIL 오류 원인
# =========================================================

def get_failure_reasons(
    result_data: dict,
) -> list[str]:

    for key in [
        "final_reasons",
        "reasons",
    ]:

        reasons = (
            result_data.get(
                key
            )
        )

        if isinstance(
            reasons,
            list,
        ):

            cleaned = [
                str(reason).strip()
                for reason in reasons
                if str(reason).strip()
            ]

            if cleaned:
                return cleaned

    reason = (
        result_data.get(
            "reason"
        )
    )

    if reason:

        return [
            str(reason).strip()
        ]

    return [
        "기준 이미지와 차이가 검출되었습니다."
    ]


def clean_failure_reason(
    reason: str,
) -> str:

    text = str(
        reason
    ).strip()

    if not text:

        return (
            "기준 이미지와 차이가 검출되었습니다."
        )

    text = re.sub(
        r":\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\s*="
        r".*$",
        "",
        text,
    )

    text = re.sub(
        r"\b"
        r"[A-Za-z_][A-Za-z0-9_]*"
        r"\s*=\s*"
        r"[-+]?"
        r"(?:\d+(?:\.\d*)?|\.\d+)"
        r"\b",
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

        text = re.sub(
            rf"\b{re.escape(term)}\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(
        r"\s*,\s*,+",
        ", ",
        text,
    )

    text = re.sub(
        r",\s*$",
        "",
        text,
    )

    text = re.sub(
        r":\s*$",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if text.endswith(
        "검출됨"
    ):

        text = (
            text[:-3]
            + "검출되었습니다."
        )

    elif text.endswith(
        "발생함"
    ):

        text = (
            text[:-3]
            + "발생했습니다."
        )

    elif not text.endswith(
        "."
    ):

        text += "."

    return text


# =========================================================
# 15. Category 표시명
# =========================================================

def get_category_display_name(
    value,
) -> str:

    category = str(
        value or ""
    ).strip().lower()

    category_names = {

        "text_list":
            "텍스트 목록",

        "status_time":
            "상태 · 시간",

        "guide_image":
            "안내 이미지",

        "popup":
            "팝업",

        "card_ui":
            "카드 UI",

        "setting_control":
            "설정 화면",

        "general_diff":
            "일반 화면",
    }

    return category_names.get(
        category,
        "일반 화면",
    )


# =========================================================
# 16. 기존 모델 새 판독 관련 함수
# =========================================================

def get_latest_round(
    model: dict,
) -> dict | None:

    rounds = model.get(
        "rounds",
        [],
    )

    if not rounds:
        return None

    return max(
        rounds,
        key=lambda item: int(
            item.get(
                "round_number",
                0,
            )
        ),
    )


def get_next_round_number(
    model: dict,
) -> int:

    latest_round = (
        get_latest_round(
            model
        )
    )

    if latest_round is None:
        return 1

    return (
        int(
            latest_round.get(
                "round_number",
                0,
            )
        )
        + 1
    )


def build_next_scenario_id(
    model: dict,
) -> str:

    model_id = str(
        model.get(
            "model_id",
            "",
        )
    ).strip()

    next_round = (
        get_next_round_number(
            model
        )
    )

    return (
        f"{model_id}_round_"
        f"{next_round}"
    )


def get_latest_reference_dir(
    model: dict,
) -> Path | None:

    latest_round = (
        get_latest_round(
            model
        )
    )

    if not latest_round:
        return None

    reference_value = (
        latest_round.get(
            "reference_dir"
        )
    )

    if not reference_value:
        return None

    reference_path = Path(
        reference_value
    )

    if not reference_path.exists():
        return None

    return reference_path


# =========================================================
# 17. 이미지 업로드 관련 함수
# =========================================================

def get_uploaded_file_names(
    uploaded_files,
) -> list[str]:

    if not uploaded_files:
        return []

    return [
        Path(
            uploaded.name
        ).name
        for uploaded in uploaded_files
    ]


def save_uploaded_images(
    uploaded_files,
    destination_dir: Path,
) -> int:

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_count = 0

    for uploaded in uploaded_files:

        safe_name = Path(
            uploaded.name
        ).name

        target_path = (
            destination_dir
            / safe_name
        )

        with target_path.open(
            "wb"
        ) as file:

            file.write(
                uploaded.getbuffer()
            )

        saved_count += 1

    return saved_count


def save_uploaded_capture_images(
    uploaded_files,
    destination_dir: Path,
) -> int:

    return save_uploaded_images(
        uploaded_files,
        destination_dir,
    )


def remove_incomplete_scenario(
    scenario_id: str,
) -> None:

    data_dir = (
        scenario_data_dir(
            scenario_id
        )
    )

    results_dir = (
        scenario_results_dir(
            scenario_id
        )
    )

    completed_result = (
        results_dir
        / "inspection_results.json"
    )

    if completed_result.exists():

        raise FileExistsError(
            "이미 완료된 판독입니다."
        )

    if data_dir.exists():

        shutil.rmtree(
            data_dir
        )

    if results_dir.exists():

        shutil.rmtree(
            results_dir
        )


# =========================================================
# 18. 공통 Header
# =========================================================

def render_header() -> None:

    with st.container(
        border=True
    ):

        st.title(
            "NEXIS LCD Inspection System"
        )

        st.caption(
            "LCD Reference · Capture 이미지 자동 판독 시스템"
        )


# =========================================================
# 19. HOME 모델 카드
# =========================================================

def render_model_card(
    model: dict,
) -> None:

    model_id = str(
        model.get(
            "model_id",
            "",
        )
    )

    model_name = str(
        model.get(
            "model_name",
            model_id,
        )
    )

    inspection_count = int(
        model.get(
            "inspection_count",
            0,
        )
        or 0
    )

    latest_round = (
        model.get(
            "latest_round_number"
        )
    )

    reference_count = int(
        model.get(
            "reference_count",
            0,
        )
        or 0
    )

    pass_count = int(
        model.get(
            "latest_pass_count",
            0,
        )
        or 0
    )

    fail_count = int(
        model.get(
            "latest_fail_count",
            0,
        )
        or 0
    )

    with st.container(
        border=True
    ):

        st.subheader(
            model_name
        )

        if latest_round:

            st.caption(
                f"최근 판독 {latest_round}차"
            )

        else:

            st.caption(
                "판독 이력 없음"
            )

        cols = st.columns(5)

        cols[0].metric(
            "현재 정확도",
            format_accuracy(
                model.get(
                    "latest_accuracy"
                )
            ),
        )

        cols[1].metric(
            "판독 횟수",
            f"{inspection_count}회",
        )

        cols[2].metric(
            "Reference",
            f"{reference_count}개",
        )

        cols[3].metric(
            "PASS",
            pass_count,
        )

        cols[4].metric(
            "FAIL",
            fail_count,
        )

        button1, button2, spacer = (
            st.columns(
                [1.3, 1.3, 3]
            )
        )

        with button1:

            if st.button(
                "모델 상세 보기",
                key=(
                    f"open_model_"
                    f"{model_id}"
                ),
                use_container_width=True,
            ):

                go_to_view(
                    "model_detail",
                    model_id=model_id,
                )

        with button2:

            st.button(
                "모델 리포트",
                key=(
                    f"report_"
                    f"{model_id}"
                ),
                disabled=True,
                use_container_width=True,
            )


# =========================================================
# 20. HOME
# =========================================================

def render_home() -> None:

    render_header()

    st.write("")

    title_col, create_col = (
        st.columns(
            [5, 1.5]
        )
    )

    with title_col:

        st.header(
            "검사 모델 관리"
        )

        st.caption(
            "등록된 검사 모델의 최신 판독 결과와 "
            "판독 이력을 확인합니다."
        )

    with create_col:

        st.write("")

        if st.button(
            "＋ 새 모델 생성",
            type="primary",
            use_container_width=True,
        ):

            go_to_view(
                "model_create"
            )

    models = (
        load_models_from_scenarios()
    )

    if not models:

        st.info(
            "등록된 검사 모델이 없습니다."
        )

        return

    for model in models:

        render_model_card(
            model
        )

        st.write("")


# =========================================================
# 21. MODEL DETAIL
# =========================================================

def render_model_detail() -> None:

    render_header()

    st.write("")

    if st.button(
        "← 모델 목록",
        key="back_to_model_list",
    ):

        go_to_view(
            "home"
        )

    model_id = (
        st.session_state.get(
            "selected_model_id"
        )
    )

    if not model_id:

        st.error(
            "선택된 모델이 없습니다."
        )

        return

    model = (
        load_model_from_scenarios(
            str(model_id)
        )
    )

    if not model:

        st.error(
            "모델 정보를 불러오지 못했습니다."
        )

        return

    model_name = str(
        model.get(
            "model_name",
            "Model",
        )
    )

    st.header(
        model_name
    )

    st.caption(
        "모델의 전체 판독 이력과 "
        "차수별 결과를 확인합니다."
    )

    with st.container(
        border=True
    ):

        cols = st.columns(4)

        cols[0].metric(
            "Reference",
            f"{model.get('reference_count', 0)}개",
        )

        cols[1].metric(
            "판독 횟수",
            f"{model.get('inspection_count', 0)}회",
        )

        cols[2].metric(
            "현재 정확도",
            format_accuracy(
                model.get(
                    "latest_accuracy"
                )
            ),
        )

        latest_round = (
            model.get(
                "latest_round_number"
            )
        )

        cols[3].metric(
            "최근 판독",
            (
                f"{latest_round}차"
                if latest_round
                else "-"
            ),
        )

    st.subheader(
        "판독 이력"
    )

    rounds = sorted(
        model.get(
            "rounds",
            [],
        ),
        key=lambda item: int(
            item.get(
                "round_number",
                0,
            )
        ),
        reverse=True,
    )

    for round_data in rounds:

        scenario_id = str(
            round_data.get(
                "scenario_id",
                "",
            )
        )

        round_number = int(
            round_data.get(
                "round_number",
                0,
            )
            or 0
        )

        with st.container(
            border=True
        ):

            st.subheader(
                f"{round_number}차 판독"
            )

            cols = st.columns(
                [1, 1, 1, 1, 1.3]
            )

            cols[0].metric(
                "Capture",
                f"{round_data.get('capture_count', 0)}개",
            )

            cols[1].metric(
                "PASS",
                round_data.get(
                    "pass_count",
                    0,
                ),
            )

            cols[2].metric(
                "FAIL",
                round_data.get(
                    "fail_count",
                    0,
                ),
            )

            cols[3].metric(
                "정확도",
                format_accuracy(
                    round_data.get(
                        "accuracy"
                    )
                ),
            )

            with cols[4]:

                st.write("")

                if st.button(
                    "결과 보기",
                    key=(
                        f"open_result_"
                        f"{scenario_id}"
                    ),
                    use_container_width=True,
                ):

                    go_to_view(
                        "inspection_result",
                        model_id=str(
                            model_id
                        ),
                        inspection_id=(
                            scenario_id
                        ),
                    )

    st.write("")

    left, center, right = (
        st.columns(
            [2, 1.5, 2]
        )
    )

    with center:

        if st.button(
            "＋ 새로운 판독",
            type="primary",
            use_container_width=True,
        ):

            go_to_view(
                "inspection_create",
                model_id=str(
                    model_id
                ),
            )


# =========================================================
# 22. 새 모델 생성
# =========================================================

def render_model_create() -> None:

    render_header()

    st.write("")

    if st.button(
        "← 모델 목록",
        key="back_model_create",
    ):

        go_to_view(
            "home"
        )

    try:

        new_model = (
            get_next_model_info()
        )

    except RuntimeError:

        st.error(
            "새로운 모델 이름을 생성하지 못했습니다."
        )

        return

    model_id = str(
        new_model[
            "model_id"
        ]
    )

    model_name = str(
        new_model[
            "model_name"
        ]
    )

    scenario_id = str(
        new_model[
            "scenario_id"
        ]
    )

    # =====================================================
    # 제목
    # =====================================================

    st.header(
        "새 검사 모델 생성"
    )

    st.caption(
        "Reference와 Capture 이미지를 등록하고 "
        "새로운 검사 모델의 판독 기준을 설정합니다."
    )

    st.write("")

    # =====================================================
    # 1. 모델 정보
    # =====================================================

    st.subheader(
        "1. 모델 정보"
    )

    with st.container(
        border=True
    ):

        info_col1, info_col2 = (
            st.columns(
                [1, 2]
            )
        )

        with info_col1:

            st.metric(
                "새 모델",
                model_name,
            )

        with info_col2:

            st.metric(
                "최초 판독",
                "1차",
            )

        model_description = (
            st.text_input(
                "모델 설명",
                placeholder=(
                    "예: 건조기 LCD 신규 UI 검사 모델"
                ),
            )
        )

    st.write("")

    # =====================================================
    # 2. 판독 화면 유형
    # =====================================================

    st.subheader(
        "2. 판독 화면 유형"
    )

    st.caption(
        "이 모델에서 주로 검사할 LCD 화면의 "
        "형태를 선택하세요."
    )

    profile_keys = list(
        PROFILE_DISPLAY_NAMES.keys()
    )

    selected_profile = (
        st.radio(
            "화면 유형",
            options=profile_keys,
            format_func=lambda key:
                PROFILE_DISPLAY_NAMES.get(
                    key,
                    key,
                ),
            horizontal=True,
            label_visibility="collapsed",
        )
    )

    with st.container(
        border=True
    ):

        st.write(
            f"**{PROFILE_DISPLAY_NAMES.get(selected_profile)}**"
        )

        st.caption(
            PROFILE_HELP_TEXT.get(
                selected_profile,
                "",
            )
        )

    st.write("")

    # =====================================================
    # 3. 중점 판독 항목
    # =====================================================

    st.subheader(
        "3. 중점 판독 항목"
    )

    st.caption(
        "판독 과정에서 중요하게 확인할 항목을 "
        "선택하세요."
    )

    defaults = (
        get_default_enabled_checks()
    )

    selected_checks = {}

    with st.container(
        border=True
    ):

        row1 = st.columns(3)

        check_keys = list(
            CHECK_DISPLAY_NAMES.keys()
        )

        for index, check_key in enumerate(
            check_keys[:3]
        ):

            with row1[index]:

                selected_checks[
                    check_key
                ] = st.checkbox(
                    CHECK_DISPLAY_NAMES[
                        check_key
                    ],
                    value=defaults.get(
                        check_key,
                        True,
                    ),
                    help=CHECK_HELP_TEXT.get(
                        check_key
                    ),
                    key=(
                        f"new_model_check_"
                        f"{check_key}"
                    ),
                )

        row2 = st.columns(3)

        for index, check_key in enumerate(
            check_keys[3:]
        ):

            with row2[index]:

                selected_checks[
                    check_key
                ] = st.checkbox(
                    CHECK_DISPLAY_NAMES[
                        check_key
                    ],
                    value=defaults.get(
                        check_key,
                        True,
                    ),
                    help=CHECK_HELP_TEXT.get(
                        check_key
                    ),
                    key=(
                        f"new_model_check_"
                        f"{check_key}"
                    ),
                )

    selected_check_count = sum(
        1
        for enabled in (
            selected_checks.values()
        )
        if enabled
    )

    if selected_check_count == 0:

        st.warning(
            "최소 한 개 이상의 판독 항목을 선택해주세요."
        )

    else:

        st.caption(
            f"현재 {selected_check_count}개의 "
            f"판독 항목이 선택되어 있습니다."
        )

    st.write("")

    # =====================================================
    # 4. Reference 이미지 등록
    # =====================================================

    st.subheader(
        "4. Reference 이미지 등록"
    )

    st.caption(
        "새 모델의 정상 기준으로 사용할 "
        "Reference 이미지를 등록하세요."
    )

    reference_files = (
        st.file_uploader(
            "Reference 이미지 선택",
            type=[
                "png",
                "jpg",
                "jpeg",
                "bmp",
            ],
            accept_multiple_files=True,
            key="new_model_reference_upload",
            label_visibility="collapsed",
        )
    )

    reference_names = (
        get_uploaded_file_names(
            reference_files
        )
    )

    reference_name_set = set(
        reference_names
    )

    st.write("")

    # =====================================================
    # 5. Capture 이미지 등록
    # =====================================================

    st.subheader(
        "5. Capture 이미지 등록"
    )

    st.caption(
        "최초 1차 판독에 사용할 Capture 이미지를 "
        "등록하세요."
    )

    capture_files = (
        st.file_uploader(
            "Capture 이미지 선택",
            type=[
                "png",
                "jpg",
                "jpeg",
                "bmp",
            ],
            accept_multiple_files=True,
            key="new_model_capture_upload",
            label_visibility="collapsed",
        )
    )

    capture_names = (
        get_uploaded_file_names(
            capture_files
        )
    )

    capture_name_set = set(
        capture_names
    )

    # =====================================================
    # 파일 검증
    # =====================================================

    reference_duplicate_count = (
        len(reference_names)
        - len(reference_name_set)
    )

    capture_duplicate_count = (
        len(capture_names)
        - len(capture_name_set)
    )

    matched_names = (
        reference_name_set
        & capture_name_set
    )

    missing_capture = (
        reference_name_set
        - capture_name_set
    )

    extra_capture = (
        capture_name_set
        - reference_name_set
    )

    st.write("")

    with st.container(
        border=True
    ):

        status_cols = (
            st.columns(3)
        )

        status_cols[0].metric(
            "Reference",
            f"{len(reference_names)}개",
        )

        status_cols[1].metric(
            "Capture",
            f"{len(capture_names)}개",
        )

        status_cols[2].metric(
            "매칭 완료",
            f"{len(matched_names)}개",
        )

    images_ready = False

    if (
        not reference_files
        and not capture_files
    ):

        st.info(
            "Reference와 Capture 이미지를 등록해주세요."
        )

    elif not reference_files:

        st.warning(
            "Reference 이미지를 등록해주세요."
        )

    elif not capture_files:

        st.warning(
            "Capture 이미지를 등록해주세요."
        )

    elif reference_duplicate_count > 0:

        st.error(
            "Reference 이미지에 중복된 파일명이 있습니다."
        )

    elif capture_duplicate_count > 0:

        st.error(
            "Capture 이미지에 중복된 파일명이 있습니다."
        )

    elif missing_capture:

        st.warning(
            "일부 Reference 이미지와 일치하는 "
            "Capture 이미지가 없습니다."
        )

    elif extra_capture:

        st.warning(
            "Reference에 없는 Capture 이미지가 "
            "포함되어 있습니다."
        )

    elif (
        reference_name_set
        == capture_name_set
        and reference_name_set
    ):

        images_ready = True

        st.success(
            "Reference와 Capture 이미지의 "
            "파일 매칭이 완료되었습니다."
        )

    # =====================================================
    # 최종 준비 상태
    # =====================================================

    settings_ready = (
        selected_check_count
        > 0
    )

    ready_to_create = (
        images_ready
        and settings_ready
    )

    st.write("")

    # =====================================================
    # 모델 생성 버튼
    # =====================================================

    left, center, right = (
        st.columns(
            [2, 2, 2]
        )
    )

    with center:

        create_clicked = (
            st.button(
                "모델 생성 및 1차 판독 시작",
                type="primary",
                use_container_width=True,
                disabled=(
                    not ready_to_create
                ),
            )
        )

    # =====================================================
    # 실제 모델 생성
    # =====================================================

    if create_clicked:

        progress = (
            st.progress(
                0,
                text=(
                    "새 모델을 준비하고 있습니다."
                ),
            )
        )

        try:

            # -------------------------------------------------
            # 1. 동일 Scenario 존재 여부 확인
            # -------------------------------------------------

            progress.progress(
                10,
                text=(
                    "모델 저장 공간을 준비하고 있습니다."
                ),
            )

            remove_incomplete_scenario(
                scenario_id
            )

            # -------------------------------------------------
            # 2. Scenario 생성
            # -------------------------------------------------

            create_scenario(
                scenario_id,
                (
                    f"{model_name} "
                    f"1차 판독"
                ),
            )

            # -------------------------------------------------
            # 3. 모델별 판독 설정 저장
            # -------------------------------------------------

            progress.progress(
                20,
                text=(
                    "판독 설정을 저장하고 있습니다."
                ),
            )

            save_scenario_inspection_settings(
                scenario_id,
                model_name=model_name,
                model_description=(
                    model_description
                ),
                profile_key=(
                    selected_profile
                ),
                enabled_checks=(
                    selected_checks
                ),
            )

            # -------------------------------------------------
            # 4. Reference 저장
            # -------------------------------------------------

            progress.progress(
                30,
                text=(
                    "Reference 이미지를 저장하고 있습니다."
                ),
            )

            target_reference_dir = (
                scenario_reference_dir(
                    scenario_id
                )
            )

            saved_reference_count = (
                save_uploaded_images(
                    reference_files,
                    target_reference_dir,
                )
            )

            if (
                saved_reference_count
                != len(
                    reference_names
                )
            ):

                raise RuntimeError(
                    "Reference 이미지 저장 실패"
                )

            # -------------------------------------------------
            # 5. Capture 저장
            # -------------------------------------------------

            progress.progress(
                40,
                text=(
                    "Capture 이미지를 저장하고 있습니다."
                ),
            )

            target_capture_dir = (
                scenario_capture_dir(
                    scenario_id
                )
            )

            saved_capture_count = (
                save_uploaded_images(
                    capture_files,
                    target_capture_dir,
                )
            )

            if (
                saved_capture_count
                != len(
                    capture_names
                )
            ):

                raise RuntimeError(
                    "Capture 이미지 저장 실패"
                )

            # -------------------------------------------------
            # 6. 실제 저장된 파일 재검증
            # -------------------------------------------------

            saved_reference_names = (
                image_names(
                    target_reference_dir
                )
            )

            saved_capture_names = (
                image_names(
                    target_capture_dir
                )
            )

            if (
                saved_reference_names
                != saved_capture_names
            ):

                raise RuntimeError(
                    "Reference와 Capture "
                    "파일 매칭 실패"
                )

            # -------------------------------------------------
            # 7. 판독 엔진 실행
            # -------------------------------------------------

            progress.progress(
                50,
                text=(
                    "새 모델의 1차 판독을 진행하고 있습니다."
                ),
            )

            with st.spinner(
                "판독 엔진이 이미지를 분석하고 있습니다."
            ):

                run_module_for_scenario(
                    scenario_id,
                    "modules.inspector",
                )

            # -------------------------------------------------
            # 8. 결과 확인
            # -------------------------------------------------

            progress.progress(
                90,
                text=(
                    "판독 결과를 확인하고 있습니다."
                ),
            )

            result_file = (
                scenario_results_dir(
                    scenario_id
                )
                / "inspection_results.json"
            )

            if not result_file.exists():

                raise RuntimeError(
                    "판독 결과 생성 실패"
                )

            progress.progress(
                100,
                text=(
                    "새 모델 생성이 완료되었습니다."
                ),
            )

            # -------------------------------------------------
            # 9. 결과 화면으로 이동
            # -------------------------------------------------

            go_to_view(
                "inspection_result",
                model_id=model_id,
                inspection_id=scenario_id,
            )

        except FileExistsError:

            st.error(
                "동일한 모델의 1차 판독이 "
                "이미 존재합니다."
            )

        except Exception:

            st.error(
                "새 모델을 생성하지 못했습니다. "
                "이미지 구성과 판독 설정을 확인해주세요."
            )


# =========================================================
# 23. PASS 이미지 그리드
# =========================================================

def render_pass_image_grid(
    pass_results,
    capture_dir: Path,
) -> None:

    if not pass_results:

        st.info(
            "PASS 판독 결과가 없습니다."
        )

        return

    column_count = 3

    for start in range(
        0,
        len(pass_results),
        column_count,
    ):

        columns = st.columns(
            column_count
        )

        row = (
            pass_results[
                start:
                start + column_count
            ]
        )

        for index, (
            result_key,
            result_data,
        ) in enumerate(row):

            with columns[index]:

                image_path = (
                    find_capture_image(
                        capture_dir,
                        result_key,
                        result_data,
                    )
                )

                display_name = (
                    get_display_file_name(
                        result_key,
                        result_data,
                    )
                )

                if image_path:

                    st.image(
                        str(
                            image_path
                        ),
                        use_container_width=True,
                    )

                else:

                    st.warning(
                        "이미지를 찾을 수 없습니다."
                    )

                st.caption(
                    display_name
                )


# =========================================================
# 24. FAIL 이미지 그리드
# =========================================================

def render_fail_image_grid(
    fail_results,
    capture_dir: Path,
    *,
    model_id: str,
    scenario_id: str,
) -> None:

    if not fail_results:

        st.success(
            "FAIL 판독 결과가 없습니다."
        )

        return

    column_count = 3

    for start in range(
        0,
        len(fail_results),
        column_count,
    ):

        columns = st.columns(
            column_count
        )

        row = (
            fail_results[
                start:
                start + column_count
            ]
        )

        for index, (
            result_key,
            result_data,
        ) in enumerate(row):

            with columns[index]:

                image_path = (
                    find_fail_display_image(
                        capture_dir,
                        result_key,
                        result_data,
                    )
                )

                display_name = (
                    get_display_file_name(
                        result_key,
                        result_data,
                    )
                )

                if image_path:

                    st.image(
                        str(
                            image_path
                        ),
                        use_container_width=True,
                    )

                else:

                    st.warning(
                        "이미지를 찾을 수 없습니다."
                    )

                st.caption(
                    display_name
                )

                if st.button(
                    "상세 보기",
                    key=(
                        f"fail_detail_"
                        f"{scenario_id}_"
                        f"{result_key}"
                    ),
                    use_container_width=True,
                ):

                    go_to_view(
                        "image_detail",
                        model_id=model_id,
                        inspection_id=scenario_id,
                        file_name=result_key,
                    )


# =========================================================
# 25. 판독 결과 화면
# =========================================================

def render_inspection_result() -> None:

    render_header()

    model_id = (
        st.session_state.get(
            "selected_model_id"
        )
    )

    scenario_id = (
        st.session_state.get(
            "selected_inspection_id"
        )
    )

    if st.button(
        "← 모델 상세",
        key="back_to_model_detail",
    ):

        go_to_view(
            "model_detail",
            model_id=str(
                model_id
            ),
        )

    if (
        not model_id
        or not scenario_id
    ):

        st.error(
            "판독 정보를 찾을 수 없습니다."
        )

        return

    model = (
        load_model_from_scenarios(
            str(model_id)
        )
    )

    scenario = (
        load_scenario_by_id(
            str(scenario_id)
        )
    )

    if not model:

        st.error(
            "모델 정보를 불러오지 못했습니다."
        )

        return

    round_number = (
        get_round_number(
            model,
            str(scenario_id),
        )
    )

    model_name = str(
        model.get(
            "model_name",
            "Model",
        )
    )

    st.header(
        f"{model_name} · "
        f"{round_number}차 판독 결과"
    )

    st.caption(
        "판독 결과를 확인하고 "
        "개별 이미지의 상세 결과를 확인합니다."
    )

    capture_dir_value = (
        scenario.get(
            "capture_dir"
        )
    )

    capture_dir = (
        Path(
            capture_dir_value
        )
        if capture_dir_value
        else Path()
    )

    with st.container(
        border=True
    ):

        cols = st.columns(4)

        cols[0].metric(
            "전체 판독",
            f"{scenario.get('capture_count', 0)}개",
        )

        cols[1].metric(
            "PASS",
            scenario.get(
                "pass_count",
                0,
            ),
        )

        cols[2].metric(
            "FAIL",
            scenario.get(
                "fail_count",
                0,
            ),
        )

        cols[3].metric(
            "PASS 비율",
            format_accuracy(
                scenario.get(
                    "accuracy"
                )
            ),
        )

    (
        pass_results,
        fail_results,
    ) = split_results_by_status(
        scenario.get(
            "results_mapping",
            {},
        )
    )

    fail_tab, pass_tab = st.tabs(
        [
            f"FAIL {len(fail_results)}",
            f"PASS {len(pass_results)}",
        ]
    )

    with fail_tab:

        st.subheader(
            "FAIL"
        )

        st.caption(
            "오류가 검출된 Capture 이미지입니다."
        )

        render_fail_image_grid(
            fail_results,
            capture_dir,
            model_id=str(
                model_id
            ),
            scenario_id=str(
                scenario_id
            ),
        )

    with pass_tab:

        st.subheader(
            "PASS"
        )

        st.caption(
            "정상 판정된 Capture 이미지입니다."
        )

        render_pass_image_grid(
            pass_results,
            capture_dir,
        )


# =========================================================
# 26. FAIL 상세 화면
# =========================================================

def render_image_detail() -> None:

    render_header()

    model_id = (
        st.session_state.get(
            "selected_model_id"
        )
    )

    scenario_id = (
        st.session_state.get(
            "selected_inspection_id"
        )
    )

    file_key = (
        st.session_state.get(
            "selected_file_name"
        )
    )

    if st.button(
        "← 판독 결과",
        key="back_from_detail",
    ):

        go_to_view(
            "inspection_result",
            model_id=str(
                model_id
            ),
            inspection_id=str(
                scenario_id
            ),
        )

    if not scenario_id:

        st.error(
            "판독 정보를 찾을 수 없습니다."
        )

        return

    scenario = (
        load_scenario_by_id(
            str(scenario_id)
        )
    )

    results_mapping = (
        scenario.get(
            "results_mapping",
            {},
        )
    )

    result_data = (
        results_mapping.get(
            str(file_key),
            {},
        )
    )

    if not result_data:

        st.error(
            "해당 이미지의 판독 결과를 "
            "찾을 수 없습니다."
        )

        return

    display_name = (
        get_display_file_name(
            str(file_key),
            result_data,
        )
    )

    status = str(
        result_data.get(
            "final_status",
            "",
        )
    ).strip().upper()

    reference_dir_value = (
        scenario.get(
            "reference_dir"
        )
    )

    capture_dir_value = (
        scenario.get(
            "capture_dir"
        )
    )

    reference_dir = (
        Path(
            reference_dir_value
        )
        if reference_dir_value
        else Path()
    )

    capture_dir = (
        Path(
            capture_dir_value
        )
        if capture_dir_value
        else Path()
    )

    reference_image = (
        find_reference_image(
            reference_dir,
            str(file_key),
            result_data,
        )
    )

    capture_image = (
        find_fail_display_image(
            capture_dir,
            str(file_key),
            result_data,
        )
    )

    # =====================================================
    # 파일명 + 상태
    # =====================================================

    if status == "FAIL":

        st.markdown(
            f"## {display_name} **[FAIL]**"
        )

    elif status == "PASS":

        st.markdown(
            f"## {display_name} **[PASS]**"
        )

    else:

        st.markdown(
            f"## {display_name}"
        )

    # =====================================================
    # Reference / Capture
    # =====================================================

    reference_column, capture_column = (
        st.columns(
            2,
            gap="small",
        )
    )

    with reference_column:

        with st.container(
            border=True
        ):

            st.markdown(
                "**Reference**"
            )

            st.caption(
                "정상 기준 이미지"
            )

            if reference_image:

                st.image(
                    str(
                        reference_image
                    ),
                    use_container_width=True,
                )

            else:

                st.warning(
                    "Reference 이미지를 찾을 수 없습니다."
                )

    with capture_column:

        with st.container(
            border=True
        ):

            st.markdown(
                "**Capture**"
            )

            st.caption(
                "판독 대상 이미지"
            )

            if capture_image:

                st.image(
                    str(
                        capture_image
                    ),
                    use_container_width=True,
                )

            else:

                st.warning(
                    "Capture 이미지를 찾을 수 없습니다."
                )

    # =====================================================
    # 오류 원인
    # =====================================================

    if status == "FAIL":

        st.markdown(
            "### 오류 원인"
        )

        reasons = (
            get_failure_reasons(
                result_data
            )
        )

        with st.container(
            border=True
        ):

            st.caption(
                "판독 과정에서 다음 문제가 검출되었습니다."
            )

            for reason in reasons:

                cleaned_reason = (
                    clean_failure_reason(
                        str(reason)
                    )
                )

                st.error(
                    cleaned_reason,
                    icon=None,
                )

    # =====================================================
    # 상세 판독 정보
    # =====================================================

    st.markdown(
        "#### 상세 판독 정보"
    )

    category = (
        get_category_display_name(
            result_data.get(
                "category"
            )
        )
    )

    diff_summary = (
        result_data.get(
            "diff_summary",
            {},
        )
    )

    evidence_summary = (
        result_data.get(
            "evidence_summary",
            {},
        )
    )

    if not isinstance(
        diff_summary,
        dict,
    ):

        diff_summary = {}

    if not isinstance(
        evidence_summary,
        dict,
    ):

        evidence_summary = {}

    diff_roi_count = (
        diff_summary.get(
            "diff_roi_count"
        )
    )

    if diff_roi_count is None:

        diff_roi_count = (
            evidence_summary.get(
                "diff_roi_count"
            )
        )

    total_diff_ratio = (
        diff_summary.get(
            "total_diff_area_ratio"
        )
    )

    if total_diff_ratio is None:

        total_diff_ratio = (
            evidence_summary.get(
                "total_diff_area_ratio"
            )
        )

    overall_ssim = (
        evidence_summary.get(
            "overall_ssim"
        )
    )

    minimum_roi_ssim = (
        evidence_summary.get(
            "minimum_roi_ssim"
        )
    )

    if minimum_roi_ssim is None:

        minimum_roi_ssim = (
            evidence_summary.get(
                "min_roi_ssim"
            )
        )

    with st.container(
        border=True
    ):

        (
            detail1,
            detail2,
            detail3,
            detail4,
            detail5,
        ) = st.columns(
            5,
            gap="small",
        )

        with detail1:

            st.caption(
                "검사 유형"
            )

            st.write(
                category
            )

        with detail2:

            st.caption(
                "차이 영역"
            )

            if diff_roi_count is not None:

                st.write(
                    f"{diff_roi_count}개"
                )

            else:

                st.write("-")

        with detail3:

            st.caption(
                "전체 차이 비율"
            )

            st.write(
                format_percentage_from_ratio(
                    total_diff_ratio
                )
            )

        with detail4:

            st.caption(
                "전체 유사도"
            )

            st.write(
                format_decimal(
                    overall_ssim
                )
            )

        with detail5:

            st.caption(
                "최저 유사도"
            )

            st.write(
                format_decimal(
                    minimum_roi_ssim
                )
            )


# =========================================================
# 27. 기존 모델의 새로운 판독
# =========================================================

def render_inspection_create() -> None:

    render_header()

    model_id = (
        st.session_state.get(
            "selected_model_id"
        )
    )

    if st.button(
        "← 모델 상세",
        key="back_new_inspection",
    ):

        go_to_view(
            "model_detail",
            model_id=str(
                model_id
            ),
        )

    if not model_id:

        st.error(
            "선택된 모델이 없습니다."
        )

        return

    model = (
        load_model_from_scenarios(
            str(model_id)
        )
    )

    if not model:

        st.error(
            "모델 정보를 불러오지 못했습니다."
        )

        return

    model_name = str(
        model.get(
            "model_name",
            "Model",
        )
    )

    next_round = (
        get_next_round_number(
            model
        )
    )

    next_scenario_id = (
        build_next_scenario_id(
            model
        )
    )

    latest_reference_dir = (
        get_latest_reference_dir(
            model
        )
    )

    st.header(
        f"{model_name} · "
        f"{next_round}차 판독"
    )

    st.caption(
        "새로운 Capture 이미지를 등록하여 "
        "판독을 실행합니다."
    )

    if not latest_reference_dir:

        st.error(
            "Reference 이미지를 "
            "불러오지 못했습니다."
        )

        return

    reference_names = (
        image_names(
            latest_reference_dir
        )
    )

    reference_count = len(
        reference_names
    )

    with st.container(
        border=True
    ):

        st.subheader(
            "Reference"
        )

        st.caption(
            "기존 모델에 등록된 Reference 이미지를 "
            "자동으로 사용합니다."
        )

        st.metric(
            "Reference 이미지",
            f"{reference_count}개",
        )

    st.subheader(
        "Capture 이미지 등록"
    )

    st.caption(
        "검사할 Capture 이미지들을 "
        "한 번에 선택하거나 드래그하여 등록하세요."
    )

    uploaded_files = (
        st.file_uploader(
            "Capture 이미지 선택",
            type=[
                "png",
                "jpg",
                "jpeg",
                "bmp",
            ],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
    )

    uploaded_names = (
        get_uploaded_file_names(
            uploaded_files
        )
    )

    uploaded_name_set = set(
        uploaded_names
    )

    duplicate_count = (
        len(uploaded_names)
        - len(uploaded_name_set)
    )

    matched_names = (
        reference_names
        & uploaded_name_set
    )

    missing_capture = (
        reference_names
        - uploaded_name_set
    )

    extra_capture = (
        uploaded_name_set
        - reference_names
    )

    with st.container(
        border=True
    ):

        cols = st.columns(3)

        cols[0].metric(
            "Reference",
            f"{reference_count}개",
        )

        cols[1].metric(
            "Capture",
            f"{len(uploaded_names)}개",
        )

        cols[2].metric(
            "매칭 완료",
            f"{len(matched_names)}개",
        )

    ready_to_run = False

    if not uploaded_files:

        st.info(
            "Capture 이미지를 등록해주세요."
        )

    elif duplicate_count > 0:

        st.error(
            "같은 이름의 Capture 이미지가 "
            "중복으로 포함되어 있습니다."
        )

    elif missing_capture:

        st.warning(
            "Reference와 이름이 일치하지 않는 "
            "Capture 이미지가 있습니다."
        )

        st.caption(
            f"현재 매칭된 이미지: "
            f"{len(matched_names)} / "
            f"{reference_count}"
        )

    elif extra_capture:

        st.warning(
            "Reference에 없는 Capture 이미지가 "
            "포함되어 있습니다."
        )

    elif (
        uploaded_name_set
        == reference_names
    ):

        ready_to_run = True

        st.success(
            "판독 준비가 완료되었습니다."
        )

    left, center, right = (
        st.columns(
            [2, 1.6, 2]
        )
    )

    with center:

        start_clicked = (
            st.button(
                "판독 시작",
                type="primary",
                disabled=(
                    not ready_to_run
                ),
                use_container_width=True,
            )
        )

    if start_clicked:

        progress = st.progress(
            0,
            text=(
                "판독을 준비하고 있습니다."
            ),
        )

        try:

            progress.progress(
                10,
                text=(
                    "판독 환경을 준비하고 있습니다."
                ),
            )

            remove_incomplete_scenario(
                next_scenario_id
            )

            create_scenario(
                next_scenario_id,
                (
                    f"{model_name} "
                    f"{next_round}차 판독"
                ),
            )

            progress.progress(
                20,
                text=(
                    "Reference 이미지를 "
                    "준비하고 있습니다."
                ),
            )

            target_reference_dir = (
                scenario_reference_dir(
                    next_scenario_id
                )
            )

            copied_reference_count = (
                copy_images(
                    latest_reference_dir,
                    target_reference_dir,
                )
            )

            if (
                copied_reference_count
                != reference_count
            ):

                raise RuntimeError(
                    "Reference 이미지 준비 실패"
                )

            progress.progress(
                30,
                text=(
                    "Capture 이미지를 "
                    "등록하고 있습니다."
                ),
            )

            target_capture_dir = (
                scenario_capture_dir(
                    next_scenario_id
                )
            )

            saved_capture_count = (
                save_uploaded_capture_images(
                    uploaded_files,
                    target_capture_dir,
                )
            )

            if (
                saved_capture_count
                != reference_count
            ):

                raise RuntimeError(
                    "Capture 이미지 저장 실패"
                )

            saved_reference_names = (
                image_names(
                    target_reference_dir
                )
            )

            saved_capture_names = (
                image_names(
                    target_capture_dir
                )
            )

            if (
                saved_reference_names
                != saved_capture_names
            ):

                raise RuntimeError(
                    "Reference와 Capture "
                    "파일 매칭 실패"
                )

            progress.progress(
                40,
                text=(
                    "이미지 판독을 "
                    "진행하고 있습니다."
                ),
            )

            with st.spinner(
                "판독 엔진이 이미지를 "
                "분석하고 있습니다."
            ):

                run_module_for_scenario(
                    next_scenario_id,
                    "modules.inspector",
                )

            progress.progress(
                90,
                text=(
                    "판독 결과를 "
                    "정리하고 있습니다."
                ),
            )

            result_file = (
                scenario_results_dir(
                    next_scenario_id
                )
                / "inspection_results.json"
            )

            if not result_file.exists():

                raise RuntimeError(
                    "판독 결과 생성 실패"
                )

            progress.progress(
                100,
                text=(
                    "판독이 완료되었습니다."
                ),
            )

            go_to_view(
                "inspection_result",
                model_id=str(
                    model_id
                ),
                inspection_id=(
                    next_scenario_id
                ),
            )

        except FileExistsError:

            st.error(
                "해당 판독 차수는 "
                "이미 완료되어 있습니다."
            )

        except Exception:

            st.error(
                "판독을 완료하지 못했습니다. "
                "이미지 구성을 확인한 뒤 "
                "다시 시도해주세요."
            )


# =========================================================
# 28. Router
# =========================================================

def main() -> None:

    current_view = (
        st.session_state.get(
            "current_view",
            "home",
        )
    )

    if current_view == "home":

        render_home()

    elif current_view == (
        "model_detail"
    ):

        render_model_detail()

    elif current_view == (
        "model_create"
    ):

        render_model_create()

    elif current_view == (
        "inspection_result"
    ):

        render_inspection_result()

    elif current_view == (
        "image_detail"
    ):

        render_image_detail()

    elif current_view == (
        "inspection_create"
    ):

        render_inspection_create()

    else:

        st.session_state.current_view = (
            "home"
        )

        st.rerun()


# =========================================================
# 29. 실행
# =========================================================

if __name__ == "__main__":

    main()