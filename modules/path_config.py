from pathlib import Path

# ============================================================
# 프로젝트 경로 설정 파일
# ------------------------------------------------------------
# 이 파일의 목적:
# 팀원마다 프로젝트 폴더 위치가 달라도
# data, config, results, modules 폴더를 안정적으로 찾기 위함
# ============================================================


# 현재 파일 위치:
# Nexis_LCD_Inspection/modules/path_config.py
#
# Path(__file__).resolve()
# → 현재 파일의 전체 경로
#
# parents[1]
# → modules 폴더의 상위 폴더
# → 즉, Nexis_LCD_Inspection 프로젝트 최상위 폴더
PROJECT_ROOT = Path(__file__).resolve().parents[1]


# 주요 폴더 경로
DATA_DIR = PROJECT_ROOT / "data"
REFERENCE_DIR = DATA_DIR / "reference"
CAPTURE_DIR = DATA_DIR / "capture"

CONFIG_DIR = PROJECT_ROOT / "config"
RESULTS_DIR = PROJECT_ROOT / "results"
LOGS_DIR = PROJECT_ROOT / "logs"
MODULES_DIR = PROJECT_ROOT / "modules"


# 주요 파일 경로
RESOLVED_MATCHES_PATH = RESULTS_DIR / "resolved_matches.json"
INSPECTION_RULES_PATH = CONFIG_DIR / "inspection_rules.json"
INSPECTION_RESULTS_PATH = RESULTS_DIR / "inspection_results.json"

