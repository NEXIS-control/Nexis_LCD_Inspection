import json
import subprocess
import sys
import time
from pathlib import Path

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        PROJECT_ROOT,
        RESULTS_DIR,
        RESOLVED_MATCHES_PATH,
        DETECTED_ROIS_PATH,
        INSPECTION_RESULTS_PATH,
    )
except ModuleNotFoundError:
    from path_config import (
        PROJECT_ROOT,
        RESULTS_DIR,
        RESOLVED_MATCHES_PATH,
        DETECTED_ROIS_PATH,
        INSPECTION_RESULTS_PATH,
    )


# ============================================================
# Paths
# ============================================================

MODULES_DIR = PROJECT_ROOT / "modules"

SSIM_RESULTS_PATH = RESULTS_DIR / "ssim_results.json"
OCR_RESULTS_PATH = RESULTS_DIR / "ocr_results.json"
INSPECTION_SUMMARY_CSV_PATH = RESULTS_DIR / "inspection_summary.csv"
FAIL_LIST_PATH = RESULTS_DIR / "fail_list.csv"
CATEGORY_STATUS_SUMMARY_PATH = RESULTS_DIR / "category_status_summary.csv"


# ============================================================
# Pipeline Steps
# ============================================================

PIPELINE_STEPS = [
    {
        "name": "Pair Manager",
        "description": "reference/capture 파일명 기반 매칭",
        "script": MODULES_DIR / "pair_manager.py",
        "required_output": RESOLVED_MATCHES_PATH,
    },
    {
        "name": "Diff Detector",
        "description": "reference/capture 차이 영역 자동 검출",
        "script": MODULES_DIR / "diff_detector.py",
        "required_output": DETECTED_ROIS_PATH,
    },
    {
        "name": "SSIM Checker",
        "description": "차이 ROI 이미지 유사도 검사",
        "script": MODULES_DIR / "ssim_checker.py",
        "required_output": SSIM_RESULTS_PATH,
    },
    {
        "name": "OCR Checker",
        "description": "차이 ROI OCR 텍스트 검사",
        "script": MODULES_DIR / "ocr_checker.py",
        "required_output": OCR_RESULTS_PATH,
    },
    {
        "name": "Decision Engine",
        "description": "최종 PASS / FAIL 이진 판정",
        "script": MODULES_DIR / "decision_engine.py",
        "required_output": INSPECTION_RESULTS_PATH,
    },
    {
        "name": "Result Analyzer",
        "description": "결과 요약 CSV 생성",
        "script": MODULES_DIR / "result_analyzer.py",
        "required_output": FAIL_LIST_PATH,
    },
]


# ============================================================
# Utility
# ============================================================


def print_header():
    print("\n")
    print("============================================================")
    print(" NEXIS LCD INSPECTION PIPELINE")
    print("============================================================")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"Python       : {sys.executable}")
    print("============================================================")


def run_step(step_index: int, total_steps: int, step: dict):
    """
    pipeline step 하나를 실행한다.
    """

    name = step["name"]
    description = step["description"]
    script_path = step["script"]
    required_output = step["required_output"]

    print("\n")
    print("------------------------------------------------------------")
    print(f"[{step_index}/{total_steps}] {name}")
    print("------------------------------------------------------------")
    print(f"Description : {description}")
    print(f"Script      : {script_path}")
    print(f"Output      : {required_output}")
    print("------------------------------------------------------------")

    if not script_path.exists():
        raise FileNotFoundError(f"실행 파일이 없습니다: {script_path}")

    start_time = time.time()

    process = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    elapsed = time.time() - start_time

    if process.returncode != 0:
        raise RuntimeError(
            f"{name} 실행 중 오류가 발생했습니다. "
            f"return code = {process.returncode}"
        )

    if required_output and not required_output.exists():
        raise FileNotFoundError(
            f"{name} 실행 후 필요한 결과 파일이 생성되지 않았습니다: {required_output}"
        )

    print("------------------------------------------------------------")
    print(f"{name} 완료")
    print(f"Elapsed time: {elapsed:.2f} sec")
    print("------------------------------------------------------------")


def load_inspection_summary():
    """
    decision_engine.py가 생성한 inspection_results.json에서
    최종 PASS / FAIL 개수를 읽는다.
    """
    if not INSPECTION_RESULTS_PATH.exists():
        return None

    with open(INSPECTION_RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("summary", {})


def print_final_summary(total_elapsed: float):
    """
    전체 실행 결과 요약 출력.
    """

    summary = load_inspection_summary()

    print("\n")
    print("============================================================")
    print(" FINAL INSPECTION SUMMARY")
    print("============================================================")

    if summary:
        print(f"Total items     : {summary.get('total_items')}")
        print(f"Processed count : {summary.get('processed_count')}")
        print(f"Error count     : {summary.get('error_count')}")
        print("------------------------------------------------------------")
        print(f"PASS count      : {summary.get('pass_count')}")
        print(f"FAIL count      : {summary.get('fail_count')}")
    else:
        print("inspection_results.json 요약을 읽을 수 없습니다.")

    print("------------------------------------------------------------")
    print(f"Total elapsed   : {total_elapsed:.2f} sec")
    print("------------------------------------------------------------")
    print("Generated files:")
    print(f"- {RESOLVED_MATCHES_PATH}")
    print(f"- {DETECTED_ROIS_PATH}")
    print(f"- {SSIM_RESULTS_PATH}")
    print(f"- {OCR_RESULTS_PATH}")
    print(f"- {INSPECTION_RESULTS_PATH}")
    print(f"- {INSPECTION_SUMMARY_CSV_PATH}")
    print(f"- {FAIL_LIST_PATH}")
    print(f"- {CATEGORY_STATUS_SUMMARY_PATH}")
    print("============================================================")


# ============================================================
# Main
# ============================================================


def main():
    print_header()

    total_start_time = time.time()

    total_steps = len(PIPELINE_STEPS)

    for index, step in enumerate(PIPELINE_STEPS, start=1):
        run_step(
            step_index=index,
            total_steps=total_steps,
            step=step,
        )

    total_elapsed = time.time() - total_start_time

    print_final_summary(total_elapsed)


if __name__ == "__main__":
    main()
