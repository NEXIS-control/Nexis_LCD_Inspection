from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# =========================================================
# 0. 프로젝트 경로
# =========================================================

WEBSITE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEBSITE_DIR.parent

DATA_SCENARIOS_DIR = (
    PROJECT_ROOT
    / "data"
    / "scenarios"
)

RESULT_SCENARIOS_DIR = (
    PROJECT_ROOT
    / "results"
    / "scenarios"
)

WEB_DATA_DIR = (
    PROJECT_ROOT
    / "web_data"
)

# 사용자가 직접 지정한 모델 표시 이름을 저장하는 파일.
# model_id(예: "model_a") -> 커스텀 표시 이름(예: "세탁기 LCD") 매핑.
# 이 파일이 있으면 폴더명에서 자동으로 만든 "Model A" 대신
# 여기 저장된 이름이 화면과 리포트 어디서나 우선 사용된다.
MODEL_DISPLAY_NAMES_PATH = (
    WEB_DATA_DIR
    / "model_display_names.json"
)


# =========================================================
# 1. 공통 함수
# =========================================================

def load_json(
    path: Path,
) -> dict[str, Any]:
    """
    JSON 파일을 읽는다.

    파일이 없거나 JSON 형식이 올바르지 않으면
    빈 dict를 반환한다.
    """

    if not path.exists():
        return {}

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except (
        json.JSONDecodeError,
        OSError,
    ):
        pass

    return {}


def count_images(
    folder: Path,
) -> int:
    """
    지정한 폴더 안의 이미지 개수를 계산한다.
    """

    if not folder.exists():
        return 0

    supported_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".webp",
    }

    return sum(
        1
        for path in folder.iterdir()
        if (
            path.is_file()
            and path.suffix.lower()
            in supported_extensions
        )
    )


# =========================================================
# 1-1. 모델 표시 이름(커스텀 이름) 관리
# =========================================================

def load_model_display_name_overrides() -> dict[str, str]:
    """
    사용자가 지정한 모델 표시 이름 전체를 읽는다.

    예: {"model_a": "세탁기 LCD 검사", "model_b": "건조기 LCD 검사"}
    """

    raw_data = load_json(
        MODEL_DISPLAY_NAMES_PATH
    )

    overrides: dict[str, str] = {}

    for model_key, display_name in raw_data.items():

        if not isinstance(
            display_name,
            str,
        ):
            continue

        cleaned_name = display_name.strip()

        if cleaned_name:
            overrides[str(model_key)] = cleaned_name

    return overrides


def save_model_display_name(
    model_id: str,
    display_name: str,
) -> None:
    """
    특정 모델(model_id)의 표시 이름을 저장한다.

    display_name이 빈 문자열이면 커스텀 이름을 지우고
    원래(폴더명 기반) 자동 이름으로 되돌린다.
    """

    WEB_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    overrides = load_model_display_name_overrides()

    cleaned_name = str(display_name).strip()

    if cleaned_name:
        overrides[str(model_id)] = cleaned_name
    else:
        overrides.pop(str(model_id), None)

    temporary_path = MODEL_DISPLAY_NAMES_PATH.with_suffix(
        MODEL_DISPLAY_NAMES_PATH.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            overrides,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_path.replace(
        MODEL_DISPLAY_NAMES_PATH
    )


def reset_model_display_name(
    model_id: str,
) -> None:
    """모델 이름을 원래(폴더명 기반) 자동 이름으로 되돌린다."""

    save_model_display_name(
        model_id,
        "",
    )


# =========================================================
# 2. Scenario 이름 해석
# =========================================================

def parse_scenario_name(
    scenario_name: str,
) -> dict[str, Any]:
    """
    scenario 폴더명을
    웹에서 사용할 모델/판독 차수 구조로 변환한다.

    예:

    model_a_round_1
        → Model A / 1차

    model_a_round_2
        → Model A / 2차

    model_a_round_3
        → Model A / 3차

    model_b
        → Model B / 1차
    """

    name = str(
        scenario_name
    ).strip()

    # -----------------------------------------------------
    # model_a_round_1 형식
    # -----------------------------------------------------

    round_pattern = re.fullmatch(
        r"model_([a-z0-9]+)_round_(\d+)",
        name,
        flags=re.IGNORECASE,
    )

    if round_pattern:

        model_token = (
            round_pattern
            .group(1)
            .upper()
        )

        round_number = int(
            round_pattern.group(2)
        )

        model_key = f"model_{model_token.lower()}"

        return {
            "scenario_id": name,

            "model_key":
                model_key,

            "model_name":
                _resolve_model_display_name(
                    model_key,
                    f"Model {model_token}",
                ),

            "round_number":
                round_number,
        }

    # -----------------------------------------------------
    # model_b 형식
    # -----------------------------------------------------

    simple_pattern = re.fullmatch(
        r"model_([a-z0-9]+)",
        name,
        flags=re.IGNORECASE,
    )

    if simple_pattern:

        model_token = (
            simple_pattern
            .group(1)
            .upper()
        )

        model_key = f"model_{model_token.lower()}"

        return {
            "scenario_id": name,

            "model_key":
                model_key,

            "model_name":
                _resolve_model_display_name(
                    model_key,
                    f"Model {model_token}",
                ),

            "round_number":
                1,
        }

    # -----------------------------------------------------
    # 그 외 이름
    # -----------------------------------------------------

    return {
        "scenario_id":
            name,

        "model_key":
            name,

        "model_name":
            _resolve_model_display_name(
                name,
                name,
            ),

        "round_number":
            1,
    }


def _resolve_model_display_name(
    model_key: str,
    default_name: str,
) -> str:
    """
    model_key에 대해 사용자가 지정한 커스텀 이름이 있으면 그것을,
    없으면 기본(폴더명 기반) 이름을 반환한다.
    """

    overrides = load_model_display_name_overrides()

    return overrides.get(
        model_key,
        default_name,
    )


# =========================================================
# 3. inspection_results.json 결과 정규화
# =========================================================

def extract_results_mapping(
    inspection_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    inspection_results.json 내부의
    results 항목을 dict로 정규화한다.

    엔진 버전에 따라 results가
    dict 또는 list 형태여도 대응한다.
    """

    raw_results = (
        inspection_data.get(
            "results",
            {},
        )
    )

    # -----------------------------------------------------
    # dict 구조
    # -----------------------------------------------------

    if isinstance(
        raw_results,
        dict,
    ):

        return {
            str(key): value
            for key, value
            in raw_results.items()
            if isinstance(
                value,
                dict,
            )
        }

    # -----------------------------------------------------
    # list 구조
    # -----------------------------------------------------

    if isinstance(
        raw_results,
        list,
    ):

        normalized: dict[
            str,
            dict[str, Any],
        ] = {}

        for index, item in enumerate(
            raw_results
        ):

            if not isinstance(
                item,
                dict,
            ):
                continue

            file_name = (
                item.get(
                    "file_name"
                )
                or item.get(
                    "screen_id"
                )
                or f"item_{index}"
            )

            normalized[
                str(file_name)
            ] = item

        return normalized

    return {}


# =========================================================
# 4. PASS / FAIL 개수 계산
# =========================================================

def calculate_status_counts(
    results_mapping: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, int]:
    """
    final_status 값을 기준으로
    PASS / FAIL / REVIEW 개수를 계산한다.

    현재 새 엔진은 PASS/FAIL 중심이지만
    예전 결과 파일 호환성을 위해
    REVIEW도 읽을 수 있도록 남겨둔다.
    """

    pass_count = 0
    fail_count = 0
    review_count = 0

    for result in (
        results_mapping.values()
    ):

        status = str(
            result.get(
                "final_status",
                "",
            )
        ).strip().upper()

        if status == "PASS":
            pass_count += 1

        elif status == "FAIL":
            fail_count += 1

        elif status == "REVIEW":
            review_count += 1

    return {
        "pass_count":
            pass_count,

        "fail_count":
            fail_count,

        "review_count":
            review_count,
    }


# =========================================================
# 5. 웹 표시용 정확도 계산
# =========================================================

def calculate_pass_rate(
    pass_count: int,
    fail_count: int,
    review_count: int = 0,
) -> float | None:
    """
    웹에서 표시할 현재 정확도.

    현재 멘토링 설계 기준:
        PASS 이미지 수 / 전체 판독 이미지 수 × 100
    """

    total = (
        int(pass_count)
        + int(fail_count)
        + int(review_count)
    )

    if total <= 0:
        return None

    return round(
        (
            int(pass_count)
            / total
        )
        * 100,
        2,
    )


# =========================================================
# 6. 단일 Scenario 읽기
# =========================================================

def load_scenario(
    scenario_id: str,
) -> dict[str, Any]:
    """
    하나의 scenario에 대해

    data/scenarios/[scenario_id]
    +
    results/scenarios/[scenario_id]

    정보를 합쳐 웹에서 바로 사용할 수 있는
    하나의 판독 차수 데이터로 만든다.
    """

    parsed = parse_scenario_name(
        scenario_id
    )

    # -----------------------------------------------------
    # 기본 경로
    # -----------------------------------------------------

    data_dir = (
        DATA_SCENARIOS_DIR
        / scenario_id
    )

    result_dir = (
        RESULT_SCENARIOS_DIR
        / scenario_id
    )

    reference_dir = (
        data_dir
        / "reference"
    )

    capture_dir = (
        data_dir
        / "capture"
    )

    # -----------------------------------------------------
    # 주요 파일
    # -----------------------------------------------------

    scenario_json_path = (
        data_dir
        / "scenario.json"
    )

    inspection_results_path = (
        result_dir
        / "inspection_results.json"
    )

    detected_rois_path = (
        result_dir
        / "detected_rois.json"
    )

    # -----------------------------------------------------
    # JSON 읽기
    # -----------------------------------------------------

    scenario_config = load_json(
        scenario_json_path
    )

    inspection_data = load_json(
        inspection_results_path
    )

    detected_rois_data = load_json(
        detected_rois_path
    )

    # -----------------------------------------------------
    # 개별 판독 결과
    # -----------------------------------------------------

    results_mapping = (
        extract_results_mapping(
            inspection_data
        )
    )

    status_counts = (
        calculate_status_counts(
            results_mapping
        )
    )

    # -----------------------------------------------------
    # 정확도
    # -----------------------------------------------------

    accuracy = (
        calculate_pass_rate(
            status_counts[
                "pass_count"
            ],
            status_counts[
                "fail_count"
            ],
            status_counts[
                "review_count"
            ],
        )
    )

    # -----------------------------------------------------
    # 이미지 개수
    # -----------------------------------------------------

    reference_count = count_images(
        reference_dir
    )

    capture_count = count_images(
        capture_dir
    )

    # -----------------------------------------------------
    # 반환
    # -----------------------------------------------------

    return {
        **parsed,

        "data_dir":
            data_dir,

        "result_dir":
            result_dir,

        "reference_dir":
            reference_dir,

        "capture_dir":
            capture_dir,

        "scenario_config":
            scenario_config,

        "inspection_results":
            inspection_data,

        "results_mapping":
            results_mapping,

        "detected_rois":
            detected_rois_data,

        "reference_count":
            reference_count,

        "capture_count":
            capture_count,

        "pass_count":
            status_counts[
                "pass_count"
            ],

        "fail_count":
            status_counts[
                "fail_count"
            ],

        "review_count":
            status_counts[
                "review_count"
            ],

        "accuracy":
            accuracy,
    }


# =========================================================
# 7. 전체 Scenario ID 탐색
# =========================================================

def discover_scenario_ids() -> list[str]:
    """
    data/scenarios
    results/scenarios

    두 위치를 모두 검색해
    존재하는 scenario ID를 찾는다.
    """

    scenario_ids: set[str] = set()

    for base_dir in [
        DATA_SCENARIOS_DIR,
        RESULT_SCENARIOS_DIR,
    ]:

        if not base_dir.exists():
            continue

        for path in (
            base_dir.iterdir()
        ):

            if path.is_dir():
                scenario_ids.add(
                    path.name
                )

    return sorted(
        scenario_ids
    )


# =========================================================
# 8. 전체 Scenario 읽기
# =========================================================

def load_all_scenarios() -> list[
    dict[str, Any]
]:
    """
    현재 존재하는 모든 scenario를 읽는다.
    """

    scenarios: list[
        dict[str, Any]
    ] = []

    for scenario_id in (
        discover_scenario_ids()
    ):

        scenarios.append(
            load_scenario(
                scenario_id
            )
        )

    scenarios.sort(
        key=lambda item: (
            str(
                item.get(
                    "model_key",
                    "",
                )
            ),
            int(
                item.get(
                    "round_number",
                    0,
                )
            ),
        )
    )

    return scenarios


# =========================================================
# 9. Scenario를 Model 단위로 묶기
# =========================================================

def load_models_from_scenarios() -> list[
    dict[str, Any]
]:
    """
    scenario 폴더들을

    Model A
        1차
        2차
        3차

    Model B
        1차

    같은 논리적인 모델 구조로 묶는다.
    """

    scenarios = (
        load_all_scenarios()
    )

    grouped_models: dict[
        str,
        dict[str, Any],
    ] = {}

    # -----------------------------------------------------
    # 모델별 그룹 생성
    # -----------------------------------------------------

    for scenario in scenarios:

        model_key = str(
            scenario.get(
                "model_key",
                "",
            )
        )

        model_name = str(
            scenario.get(
                "model_name",
                model_key,
            )
        )

        if model_key not in (
            grouped_models
        ):

            grouped_models[
                model_key
            ] = {
                "model_id":
                    model_key,

                "model_name":
                    model_name,

                "rounds": [],
            }

        grouped_models[
            model_key
        ]["rounds"].append(
            scenario
        )

    # -----------------------------------------------------
    # 모델별 최신 정보 계산
    # -----------------------------------------------------

    models: list[
        dict[str, Any]
    ] = []

    for model in (
        grouped_models.values()
    ):

        rounds = sorted(
            model[
                "rounds"
            ],
            key=lambda item: int(
                item.get(
                    "round_number",
                    0,
                )
            ),
        )

        model[
            "rounds"
        ] = rounds

        latest_round = (
            rounds[-1]
            if rounds
            else None
        )

        # -------------------------------------------------
        # 판독 이력이 존재하는 모델
        # -------------------------------------------------

        if latest_round:

            model[
                "inspection_count"
            ] = len(
                rounds
            )

            model[
                "latest_round_number"
            ] = latest_round.get(
                "round_number"
            )

            model[
                "latest_scenario_id"
            ] = latest_round.get(
                "scenario_id"
            )

            model[
                "latest_accuracy"
            ] = latest_round.get(
                "accuracy"
            )

            model[
                "latest_pass_count"
            ] = latest_round.get(
                "pass_count",
                0,
            )

            model[
                "latest_fail_count"
            ] = latest_round.get(
                "fail_count",
                0,
            )

            model[
                "reference_count"
            ] = latest_round.get(
                "reference_count",
                0,
            )

            model[
                "capture_count"
            ] = latest_round.get(
                "capture_count",
                0,
            )

        # -------------------------------------------------
        # 판독 이력이 없는 모델
        # -------------------------------------------------

        else:

            model[
                "inspection_count"
            ] = 0

            model[
                "latest_round_number"
            ] = None

            model[
                "latest_scenario_id"
            ] = None

            model[
                "latest_accuracy"
            ] = None

            model[
                "latest_pass_count"
            ] = 0

            model[
                "latest_fail_count"
            ] = 0

            model[
                "reference_count"
            ] = 0

            model[
                "capture_count"
            ] = 0

        models.append(
            model
        )

    # -----------------------------------------------------
    # Model A → Model B 순서
    # -----------------------------------------------------

    models.sort(
        key=lambda item: str(
            item.get(
                "model_name",
                "",
            )
        ).lower()
    )

    return models


# =========================================================
# 10. 특정 Model 조회
# =========================================================

def load_model_from_scenarios(
    model_id: str,
) -> dict[str, Any] | None:
    """
    model_a / model_b 등의 ID를 받아
    해당 모델 전체 정보를 반환한다.
    """

    for model in (
        load_models_from_scenarios()
    ):

        if str(
            model.get(
                "model_id"
            )
        ) == str(
            model_id
        ):

            return model

    return None


# =========================================================
# 11. 특정 Scenario 조회
# =========================================================

def load_scenario_by_id(
    scenario_id: str,
) -> dict[str, Any]:
    """
    특정 판독 차수 하나를 읽는다.

    추후:
    판독 결과 화면,
    개별 이미지 상세 화면

    에서 사용한다.
    """

    return load_scenario(
        scenario_id
    )


# =========================================================
# 12. 실행 테스트
# =========================================================

if __name__ == "__main__":

    models = (
        load_models_from_scenarios()
    )

    print(
        "========== SCENARIO MODEL TEST =========="
    )

    print(
        f"Model count: {len(models)}"
    )

    for model in models:

        print(
            "\n"
            f"[{model['model_name']}]"
        )

        print(
            f"  inspections : "
            f"{model['inspection_count']}"
        )

        print(
            f"  latest round: "
            f"{model['latest_round_number']}"
        )

        print(
            f"  reference   : "
            f"{model['reference_count']}"
        )

        print(
            f"  capture     : "
            f"{model['capture_count']}"
        )

        print(
            f"  PASS        : "
            f"{model['latest_pass_count']}"
        )

        print(
            f"  FAIL        : "
            f"{model['latest_fail_count']}"
        )

        print(
            f"  accuracy    : "
            f"{model['latest_accuracy']}"
        )

        print(
            "  rounds:"
        )

        for round_data in (
            model["rounds"]
        ):

            accuracy = (
                round_data.get(
                    "accuracy"
                )
            )

            accuracy_text = (
                f"{accuracy}%"
                if accuracy is not None
                else "-"
            )

            print(
                "   - "
                f"{round_data['scenario_id']} "
                f"/ {round_data['round_number']}차 "
                f"/ PASS {round_data['pass_count']} "
                f"/ FAIL {round_data['fail_count']} "
                f"/ {accuracy_text}"
            )

    print(
        "\n========================================="
    )