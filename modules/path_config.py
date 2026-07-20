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
# Main Directories
# ============================================================

DATA_DIR = PROJECT_ROOT / "data"
REFERENCE_DIR = DATA_DIR / "reference"
CAPTURE_DIR = DATA_DIR / "capture"

CONFIG_DIR = PROJECT_ROOT / "config"
MODULES_DIR = PROJECT_ROOT / "modules"
RESULTS_DIR = PROJECT_ROOT / "results"
TESTS_DIR = PROJECT_ROOT / "tests"


# ============================================================
# Config Files
# ============================================================

REFERENCE_REGISTRY_PATH = CONFIG_DIR / "reference_registry.csv"
INSPECTION_PROFILES_PATH = CONFIG_DIR / "inspection_profiles.json"
CRITICAL_TEXT_RULES_PATH = CONFIG_DIR / "critical_text_rules.json"


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
