import csv
import json
import shutil
from pathlib import Path
from datetime import datetime

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        PROJECT_ROOT,
        DATA_DIR,
        REFERENCE_DIR,
        CAPTURE_DIR,
        RESULTS_DIR,
        INSPECTION_RESULTS_PATH,
    )
except ModuleNotFoundError:
    from path_config import (
        PROJECT_ROOT,
        DATA_DIR,
        REFERENCE_DIR,
        CAPTURE_DIR,
        RESULTS_DIR,
        INSPECTION_RESULTS_PATH,
    )


# ============================================================
# Output Paths
# ============================================================

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
VALIDATION_PACK_DIR = RESULTS_DIR / f"validation_pack_{RUN_ID}"

VALIDATION_INDEX_CSV = VALIDATION_PACK_DIR / "validation_index.csv"
AUTO_PASS_CANDIDATES_CSV = VALIDATION_PACK_DIR / "auto_pass_candidates.csv"
MANUAL_CHECK_TARGETS_CSV = VALIDATION_PACK_DIR / "manual_check_targets.csv"


# ============================================================
# Helpers
# ============================================================


def load_inspection_results():
    if not INSPECTION_RESULTS_PATH.exists():
        raise FileNotFoundError(
            f"inspection_results.json 파일이 없습니다: {INSPECTION_RESULTS_PATH}\n"
            "먼저 python modules/inspector.py 또는 python modules/decision_engine.py 를 실행하세요."
        )

    with open(INSPECTION_RESULTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_mkdir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def copy_if_exists(src: Path, dst: Path):
    if src and src.exists():
        safe_mkdir(dst.parent)
        shutil.copy2(src, dst)
        return str(dst)
    return ""


def find_diff_debug_image(file_name: str):
    """
    diff_debug 폴더 안에서 해당 파일명과 관련된 debug 이미지를 찾는다.
    diff_detector.py의 저장 이름이 조금 달라도 찾을 수 있도록 stem 기준으로 검색한다.
    """

    stem = Path(file_name).stem
    diff_debug_dir = RESULTS_DIR / "diff_debug"

    if not diff_debug_dir.exists():
        return None

    candidates = []

    for path in diff_debug_dir.iterdir():
        if not path.is_file():
            continue

        name = path.name.lower()
        if stem.lower() in name:
            candidates.append(path)

    if candidates:
        return sorted(candidates)[0]

    return None


def get_priority(final_status: str):
    """
    사람이 볼 우선순위.
    FAIL을 가장 먼저 보고, 그다음 REVIEW를 본다.
    """

    if final_status == "FAIL":
        return 1
    if final_status == "REVIEW":
        return 2
    if final_status == "PASS":
        return 3
    return 9


def is_auto_pass_candidate(item: dict):
    """
    자동 PASS 중에서도 사람이 샘플 검증해야 하는 항목을 찾는다.
    특히 can_auto_pass_review_item 규칙으로 PASS 처리된 항목이 여기에 포함된다.
    """

    if item.get("final_status") != "PASS":
        return False

    reasons = " | ".join(item.get("final_reasons", []))

    keywords = [
        "자동 PASS",
        "작은 위치",
        "렌더링 차이",
        "spinner",
        "로딩",
        "팝업 화면",
        "카드 UI",
        "상태/시간",
        "설정 화면의 매우 작은 차이",
    ]

    for keyword in keywords:
        if keyword in reasons:
            return True

    return False


def flatten_item(item: dict):
    diff_summary = item.get("diff_summary", {})
    roi_summary = item.get("roi_decision_summary", {})

    final_reasons = " | ".join(item.get("final_reasons", []))

    return {
        "screen_id": item.get("screen_id", ""),
        "file_name": item.get("file_name", ""),
        "category": item.get("category", ""),
        "profile": item.get("profile", ""),
        "expected_result": item.get("expected_result", ""),
        "final_status": item.get("final_status", ""),
        "diff_roi_count": diff_summary.get("diff_roi_count", ""),
        "pass_roi_count": roi_summary.get("pass_count", ""),
        "review_roi_count": roi_summary.get("review_count", ""),
        "fail_roi_count": roi_summary.get("fail_count", ""),
        "total_diff_area_ratio": diff_summary.get("total_diff_area_ratio", ""),
        "fail_area_ratio_threshold": diff_summary.get("fail_area_ratio_threshold", ""),
        "is_loading_like": item.get("is_loading_like", ""),
        "memo": item.get("memo", ""),
        "final_reasons": final_reasons,
    }


def write_csv(path: Path, rows: list):
    if not rows:
        return

    safe_mkdir(path.parent)

    fieldnames = list(rows[0].keys())

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# Main Export Logic
# ============================================================


def export_validation_pack():
    data = load_inspection_results()

    results = data.get("results", {})
    summary = data.get("summary", {})

    safe_mkdir(VALIDATION_PACK_DIR)

    all_rows = []
    auto_pass_rows = []
    manual_check_rows = []

    status_counts = {
        "PASS": 0,
        "REVIEW": 0,
        "FAIL": 0,
    }

    for file_name, item in sorted(results.items()):
        final_status = item.get("final_status", "UNKNOWN")

        if final_status in status_counts:
            status_counts[final_status] += 1

        row = flatten_item(item)

        reference_src = REFERENCE_DIR / file_name
        capture_src = CAPTURE_DIR / file_name
        diff_debug_src = find_diff_debug_image(file_name)

        status_dir = VALIDATION_PACK_DIR / final_status / Path(file_name).stem

        copied_reference = copy_if_exists(
            reference_src,
            status_dir / f"reference_{file_name}",
        )

        copied_capture = copy_if_exists(
            capture_src,
            status_dir / f"capture_{file_name}",
        )

        copied_diff_debug = ""
        if diff_debug_src:
            copied_diff_debug = copy_if_exists(
                diff_debug_src,
                status_dir / diff_debug_src.name,
            )

        row["copied_reference"] = copied_reference
        row["copied_capture"] = copied_capture
        row["copied_diff_debug"] = copied_diff_debug

        all_rows.append(row)

        if is_auto_pass_candidate(item):
            auto_pass_rows.append(row)

        if final_status in {"FAIL", "REVIEW"}:
            manual_row = dict(row)
            manual_row["manual_check_priority"] = get_priority(final_status)
            manual_check_rows.append(manual_row)

    manual_check_rows = sorted(
        manual_check_rows,
        key=lambda r: (
            r["manual_check_priority"],
            r["category"],
            r["file_name"],
        ),
    )

    write_csv(VALIDATION_INDEX_CSV, all_rows)

    if auto_pass_rows:
        write_csv(AUTO_PASS_CANDIDATES_CSV, auto_pass_rows)

    if manual_check_rows:
        write_csv(MANUAL_CHECK_TARGETS_CSV, manual_check_rows)

    print("\n========== VALIDATION PACK SUMMARY ==========")
    print(f"Total items : {len(all_rows)}")
    print("---------------------------------------------")
    print(f"PASS count  : {status_counts['PASS']}")
    print(f"REVIEW count: {status_counts['REVIEW']}")
    print(f"FAIL count  : {status_counts['FAIL']}")
    print("---------------------------------------------")
    print(f"Auto PASS candidates : {len(auto_pass_rows)}")
    print(f"Manual check targets : {len(manual_check_rows)}")
    print("---------------------------------------------")
    print(f"Saved folder : {VALIDATION_PACK_DIR}")
    print(f"Saved CSV    : {VALIDATION_INDEX_CSV}")
    print(f"Saved CSV    : {AUTO_PASS_CANDIDATES_CSV}")
    print(f"Saved CSV    : {MANUAL_CHECK_TARGETS_CSV}")
    print("=============================================")


def main():
    export_validation_pack()


if __name__ == "__main__":
    main()
