import os
import re
from pathlib import Path

# ============================================================
# Project Root
# ============================================================
# 현재 파일 위치:
# Nexis_LCD_Inspection/modules/path_config.py
#
# parents[1] 의미:
# path_config.py -> modules -> Nexis_LCD_Inspection
# 즉, 프로젝트 최상위 폴더를 의미한다.
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ============================================================
# Optional Scenario Selection
# ============================================================
# 기본 실행은 지금까지와 똑같이 data/reference, data/capture, results를 쓴다.
# NEXIS_SCENARIO 환경 변수가 있으면 해당 시나리오의 data/results만 사용한다.
# 예: NEXIS_SCENARIO=model_a_round_1
# ============================================================

SCENARIO_ENV_VAR = "NEXIS_SCENARIO"
DEFAULT_SCENARIO_ID = "default"


def validate_scenario_id(value: str) -> str:
    scenario_id = (value or "").strip().lower()

    if not scenario_id or scenario_id == DEFAULT_SCENARIO_ID:
        return DEFAULT_SCENARIO_ID

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", scenario_id):
        raise ValueError(
            "NEXIS_SCENARIO는 영문 소문자, 숫자, 밑줄(_), 하이픈(-)만 "
            "사용할 수 있습니다. 예: model_a_round_1"
        )

    return scenario_id


ACTIVE_SCENARIO_ID = validate_scenario_id(os.environ.get(SCENARIO_ENV_VAR, ""))
IS_SCENARIO_MODE = ACTIVE_SCENARIO_ID != DEFAULT_SCENARIO_ID


# ============================================================
# Main Directories
# ============================================================

BASE_DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_DATA_ROOT = BASE_DATA_DIR / "scenarios"

BASE_RESULTS_DIR = PROJECT_ROOT / "results"
SCENARIO_RESULTS_ROOT = BASE_RESULTS_DIR / "scenarios"

DATA_DIR = (
    SCENARIO_DATA_ROOT / ACTIVE_SCENARIO_ID
    if IS_SCENARIO_MODE
    else BASE_DATA_DIR
)
REFERENCE_DIR = DATA_DIR / "reference"
CAPTURE_DIR = DATA_DIR / "capture"

CONFIG_DIR = PROJECT_ROOT / "config"
MODULES_DIR = PROJECT_ROOT / "modules"
RESULTS_DIR = (
    SCENARIO_RESULTS_ROOT / ACTIVE_SCENARIO_ID
    if IS_SCENARIO_MODE
    else BASE_RESULTS_DIR
)
TESTS_DIR = PROJECT_ROOT / "tests"


# ============================================================
# Config Files
# ============================================================

REFERENCE_REGISTRY_PATH = CONFIG_DIR / "reference_registry.csv"
INSPECTION_PROFILES_PATH = CONFIG_DIR / "inspection_profiles.json"
CRITICAL_TEXT_RULES_PATH = CONFIG_DIR / "critical_text_rules.json"
EXPECTED_RESULTS_OVERRIDE_PATH = DATA_DIR / "expected_results.csv"


# ============================================================
# Result Files
# ============================================================

RESOLVED_MATCHES_PATH = RESULTS_DIR / "resolved_matches.json"
DETECTED_ROIS_PATH = RESULTS_DIR / "detected_rois.json"
INSPECTION_RESULTS_PATH = RESULTS_DIR / "inspection_results.json"
REFERENCE_CONTACT_SHEET_PATH = RESULTS_DIR / "reference_contact_sheet.jpg"


# ============================================================
# Supported Image Extensions
# ============================================================

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


# ============================================================
# Utility Functions
# ============================================================


def ensure_directories():
    """
    프로젝트 실행에 필요한 기본 폴더들을 생성한다.
    이미 존재하는 폴더는 그대로 둔다.
    """
    directories = [
        BASE_DATA_DIR,
        SCENARIO_DATA_ROOT,
        BASE_RESULTS_DIR,
        SCENARIO_RESULTS_ROOT,
        DATA_DIR,
        REFERENCE_DIR,
        CAPTURE_DIR,
        CONFIG_DIR,
        MODULES_DIR,
        RESULTS_DIR,
        TESTS_DIR,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def is_image_file(path: Path) -> bool:
    """
    입력된 파일 경로가 이미지 파일인지 확인한다.
    .gitkeep, txt, zip 등은 제외된다.
    """
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def get_reference_images():
    """
    data/reference 폴더 안의 이미지 파일 목록을 반환한다.
    """
    return sorted([p for p in REFERENCE_DIR.iterdir() if is_image_file(p)])


def get_capture_images():
    """
    data/capture 폴더 안의 이미지 파일 목록을 반환한다.
    """
    return sorted([p for p in CAPTURE_DIR.iterdir() if is_image_file(p)])


def print_path_summary():
    """
    현재 프로젝트 경로와 주요 폴더 상태를 출력한다.
    path_config.py가 제대로 동작하는지 확인할 때 사용한다.
    """
    ensure_directories()

    reference_images = get_reference_images()
    capture_images = get_capture_images()

    print("========== PATH CONFIG SUMMARY ==========")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"ACTIVE_SCENARIO_ID: {ACTIVE_SCENARIO_ID}")
    print(f"IS_SCENARIO_MODE: {IS_SCENARIO_MODE}")
    print(f"DATA_DIR: {DATA_DIR}")
    print(f"REFERENCE_DIR: {REFERENCE_DIR}")
    print(f"CAPTURE_DIR: {CAPTURE_DIR}")
    print(f"CONFIG_DIR: {CONFIG_DIR}")
    print(f"RESULTS_DIR: {RESULTS_DIR}")
    print("-----------------------------------------")
    print(f"Reference image count: {len(reference_images)}")
    print(f"Capture image count: {len(capture_images)}")
    print("=========================================")


if __name__ == "__main__":
    print_path_summary()
