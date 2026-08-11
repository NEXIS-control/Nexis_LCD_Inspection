from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


# =========================================================
# 0. 프로젝트 경로
# =========================================================

WEBSITE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEBSITE_DIR.parent

WEB_DATA_DIR = PROJECT_ROOT / "web_data"
MODELS_DIR = WEB_DATA_DIR / "models"


# =========================================================
# 1. 기본 설정
# =========================================================

DEFAULT_ENABLED_CHECKS = {
    "text_content": True,
    "text_spacing": True,
    "image_structure": True,
    "gradient_color": True,
    "text_brightness": True,
    "progress_bar": True,
}


# =========================================================
# 2. 공통 함수
# =========================================================

def ensure_web_directories() -> None:
    """
    웹 모델 데이터를 저장할 기본 폴더를 생성한다.
    """
    MODELS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def _load_json(path: Path) -> dict[str, Any]:
    """
    JSON 파일을 읽는다.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"JSON 파일이 없습니다: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"JSON 최상위 구조가 객체가 아닙니다: {path}"
        )

    return data


def _save_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    """
    JSON 파일을 안전하게 저장한다.
    """
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_path.replace(path)


def _normalize_model_id(
    model_name: str,
) -> str:
    """
    모델 이름을 폴더명으로 사용할 수 있도록 변환한다.

    예:
    Model A -> model_a
    모델 A -> 모델_a
    """
    cleaned = (
        str(model_name)
        .strip()
        .lower()
        .replace(" ", "_")
    )

    allowed_characters = []

    for char in cleaned:
        if (
            char.isalnum()
            or char in {"_", "-"}
            or "\u3131" <= char <= "\uD7A3"
        ):
            allowed_characters.append(char)

    normalized = "".join(
        allowed_characters
    ).strip("_-")

    if not normalized:
        normalized = (
            "model_"
            + datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )

    return normalized


def get_model_dir(
    model_id: str,
) -> Path:
    return MODELS_DIR / model_id


def get_model_json_path(
    model_id: str,
) -> Path:
    return (
        get_model_dir(model_id)
        / "model.json"
    )


def get_model_reference_dir(
    model_id: str,
) -> Path:
    return (
        get_model_dir(model_id)
        / "reference"
    )


def get_model_inspections_dir(
    model_id: str,
) -> Path:
    return (
        get_model_dir(model_id)
        / "inspections"
    )


# =========================================================
# 3. 모델 생성
# =========================================================

def create_model(
    model_name: str,
    enabled_checks: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """
    새로운 검사 모델을 생성한다.

    현재 단계에서는:
    - 모델 이름
    - 검사 민감 요소
    - Reference 저장 폴더
    - Inspection 저장 폴더

    까지만 생성한다.
    """
    ensure_web_directories()

    model_name = str(
        model_name
    ).strip()

    if not model_name:
        raise ValueError(
            "모델 이름을 입력해야 합니다."
        )

    model_id = _normalize_model_id(
        model_name
    )

    model_dir = get_model_dir(
        model_id
    )

    if model_dir.exists():
        raise FileExistsError(
            f"이미 존재하는 모델입니다: {model_name}"
        )

    active_checks = dict(
        DEFAULT_ENABLED_CHECKS
    )

    if enabled_checks is not None:
        for key in active_checks:
            if key in enabled_checks:
                active_checks[key] = bool(
                    enabled_checks[key]
                )

    created_at = datetime.now().isoformat(
        timespec="seconds"
    )

    model_data = {
        "model_id": model_id,
        "model_name": model_name,
        "created_at": created_at,
        "updated_at": created_at,

        "enabled_checks": active_checks,

        "reference_count": 0,
        "inspection_count": 0,

        "latest_accuracy": None,
        "latest_pass_count": 0,
        "latest_fail_count": 0,
        "latest_inspection_id": None,
    }

    get_model_reference_dir(
        model_id
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    get_model_inspections_dir(
        model_id
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    _save_json(
        get_model_json_path(
            model_id
        ),
        model_data,
    )

    return model_data


# =========================================================
# 4. 모델 조회
# =========================================================

def load_model(
    model_id: str,
) -> dict[str, Any]:
    """
    특정 모델의 model.json을 읽는다.
    """
    return _load_json(
        get_model_json_path(
            model_id
        )
    )


def load_models() -> list[dict[str, Any]]:
    """
    등록된 전체 모델 목록을 반환한다.
    """
    ensure_web_directories()

    models: list[
        dict[str, Any]
    ] = []

    for model_dir in sorted(
        MODELS_DIR.iterdir(),
        key=lambda path: path.name.lower(),
    ):
        if not model_dir.is_dir():
            continue

        model_json_path = (
            model_dir
            / "model.json"
        )

        if not model_json_path.exists():
            continue

        try:
            model_data = _load_json(
                model_json_path
            )
            models.append(
                model_data
            )
        except (
            json.JSONDecodeError,
            ValueError,
        ):
            continue

    models.sort(
        key=lambda item: str(
            item.get(
                "created_at",
                "",
            )
        ),
        reverse=True,
    )

    return models


# =========================================================
# 5. 모델 수정
# =========================================================

def update_model(
    model_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """
    모델 정보를 일부 수정한다.
    """
    model_data = load_model(
        model_id
    )

    protected_keys = {
        "model_id",
        "created_at",
    }

    for key, value in updates.items():
        if key in protected_keys:
            continue

        model_data[key] = value

    model_data["updated_at"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    _save_json(
        get_model_json_path(
            model_id
        ),
        model_data,
    )

    return model_data


def update_enabled_checks(
    model_id: str,
    enabled_checks: dict[str, bool],
) -> dict[str, Any]:
    """
    모델의 시스템 민감 요소 설정을 수정한다.
    """
    model_data = load_model(
        model_id
    )

    current_checks = dict(
        DEFAULT_ENABLED_CHECKS
    )

    stored_checks = model_data.get(
        "enabled_checks",
        {},
    )

    if isinstance(
        stored_checks,
        dict,
    ):
        current_checks.update(
            stored_checks
        )

    for key in current_checks:
        if key in enabled_checks:
            current_checks[key] = bool(
                enabled_checks[key]
            )

    return update_model(
        model_id,
        {
            "enabled_checks":
                current_checks
        },
    )


# =========================================================
# 6. Reference 개수 갱신
# =========================================================

def count_reference_images(
    model_id: str,
) -> int:
    """
    모델 Reference 폴더의 이미지 개수를 계산한다.
    """
    reference_dir = (
        get_model_reference_dir(
            model_id
        )
    )

    if not reference_dir.exists():
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
        for path in reference_dir.iterdir()
        if (
            path.is_file()
            and path.suffix.lower()
            in supported_extensions
        )
    )


def refresh_reference_count(
    model_id: str,
) -> dict[str, Any]:
    """
    실제 Reference 파일 개수를 model.json에 반영한다.
    """
    reference_count = (
        count_reference_images(
            model_id
        )
    )

    return update_model(
        model_id,
        {
            "reference_count":
                reference_count
        },
    )


# =========================================================
# 7. Inspection 관리
# =========================================================

def get_inspection_dir(
    model_id: str,
    inspection_id: str,
) -> Path:
    return (
        get_model_inspections_dir(
            model_id
        )
        / inspection_id
    )


def get_inspection_json_path(
    model_id: str,
    inspection_id: str,
) -> Path:
    return (
        get_inspection_dir(
            model_id,
            inspection_id,
        )
        / "inspection.json"
    )


def load_inspections(
    model_id: str,
) -> list[dict[str, Any]]:
    """
    모델의 전체 판독 이력을 반환한다.
    """
    inspections_dir = (
        get_model_inspections_dir(
            model_id
        )
    )

    if not inspections_dir.exists():
        return []

    inspections: list[
        dict[str, Any]
    ] = []

    for inspection_dir in sorted(
        inspections_dir.iterdir(),
        key=lambda path: path.name.lower(),
    ):
        if not inspection_dir.is_dir():
            continue

        inspection_json = (
            inspection_dir
            / "inspection.json"
        )

        if not inspection_json.exists():
            continue

        try:
            inspection_data = (
                _load_json(
                    inspection_json
                )
            )

            inspections.append(
                inspection_data
            )
        except (
            json.JSONDecodeError,
            ValueError,
        ):
            continue

    inspections.sort(
        key=lambda item: int(
            item.get(
                "inspection_number",
                0,
            )
        )
    )

    return inspections


def get_next_inspection_number(
    model_id: str,
) -> int:
    """
    다음 판독 차수 번호를 반환한다.
    """
    inspections = load_inspections(
        model_id
    )

    if not inspections:
        return 1

    current_numbers = [
        int(
            inspection.get(
                "inspection_number",
                0,
            )
        )
        for inspection in inspections
    ]

    return max(
        current_numbers
    ) + 1


def create_inspection_record(
    model_id: str,
) -> dict[str, Any]:
    """
    새로운 판독 차수의 기본 기록을 생성한다.

    실제 Capture 업로드와 판독 연결은
    다음 단계에서 추가한다.
    """
    model_data = load_model(
        model_id
    )

    inspection_number = (
        get_next_inspection_number(
            model_id
        )
    )

    inspection_id = (
        f"run_{inspection_number:03d}"
    )

    inspection_dir = (
        get_inspection_dir(
            model_id,
            inspection_id,
        )
    )

    capture_dir = (
        inspection_dir
        / "capture"
    )

    result_dir = (
        inspection_dir
        / "results"
    )

    capture_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    created_at = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    inspection_data = {
        "inspection_id":
            inspection_id,

        "inspection_number":
            inspection_number,

        "model_id":
            model_id,

        "model_name":
            model_data.get(
                "model_name",
                model_id,
            ),

        "created_at":
            created_at,

        "completed_at":
            None,

        "status":
            "CREATED",

        "capture_count":
            0,

        "matched_count":
            0,

        "pass_count":
            0,

        "fail_count":
            0,

        "accuracy":
            None,

        "elapsed_seconds":
            None,
    }

    _save_json(
        get_inspection_json_path(
            model_id,
            inspection_id,
        ),
        inspection_data,
    )

    update_model(
        model_id,
        {
            "inspection_count":
                inspection_number,
        },
    )

    return inspection_data


# =========================================================
# 8. 판독 결과 반영
# =========================================================

def complete_inspection(
    model_id: str,
    inspection_id: str,
    *,
    capture_count: int,
    matched_count: int,
    pass_count: int,
    fail_count: int,
    elapsed_seconds: float,
) -> dict[str, Any]:
    """
    판독 완료 후 결과를 inspection.json과
    model.json에 반영한다.
    """
    inspection_data = _load_json(
        get_inspection_json_path(
            model_id,
            inspection_id,
        )
    )

    total = int(
        pass_count
    ) + int(
        fail_count
    )

    accuracy = (
        pass_count
        / total
        * 100
        if total > 0
        else 0.0
    )

    inspection_data.update(
        {
            "completed_at":
                datetime.now().isoformat(
                    timespec="seconds"
                ),

            "status":
                "COMPLETED",

            "capture_count":
                int(
                    capture_count
                ),

            "matched_count":
                int(
                    matched_count
                ),

            "pass_count":
                int(
                    pass_count
                ),

            "fail_count":
                int(
                    fail_count
                ),

            "accuracy":
                round(
                    accuracy,
                    2,
                ),

            "elapsed_seconds":
                round(
                    float(
                        elapsed_seconds
                    ),
                    3,
                ),
        }
    )

    _save_json(
        get_inspection_json_path(
            model_id,
            inspection_id,
        ),
        inspection_data,
    )

    update_model(
        model_id,
        {
            "latest_accuracy":
                round(
                    accuracy,
                    2,
                ),

            "latest_pass_count":
                int(
                    pass_count
                ),

            "latest_fail_count":
                int(
                    fail_count
                ),

            "latest_inspection_id":
                inspection_id,

            "inspection_count":
                int(
                    inspection_data[
                        "inspection_number"
                    ]
                ),
        },
    )

    return inspection_data


# =========================================================
# 9. 초기 실행 테스트
# =========================================================

if __name__ == "__main__":
    ensure_web_directories()

    print(
        "WEB DATA DIR:",
        WEB_DATA_DIR,
    )

    print(
        "MODELS DIR:",
        MODELS_DIR,
    )

    print(
        "MODEL COUNT:",
        len(
            load_models()
        ),
    )