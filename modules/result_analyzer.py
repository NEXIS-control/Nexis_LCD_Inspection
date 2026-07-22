import csv
from collections import Counter, defaultdict
from pathlib import Path

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import RESULTS_DIR
except ModuleNotFoundError:
    from path_config import RESULTS_DIR


# ============================================================
# Paths
# ============================================================

INSPECTION_SUMMARY_CSV_PATH = RESULTS_DIR / "inspection_summary.csv"
FAIL_REVIEW_LIST_PATH = RESULTS_DIR / "fail_review_list.csv"
CATEGORY_STATUS_SUMMARY_PATH = RESULTS_DIR / "category_status_summary.csv"


# ============================================================
# Helper Functions
# ============================================================


def load_inspection_summary():
    if not INSPECTION_SUMMARY_CSV_PATH.exists():
        raise FileNotFoundError(
            f"inspection_summary.csv 파일이 없습니다: {INSPECTION_SUMMARY_CSV_PATH}\n"
            "먼저 python modules/decision_engine.py 를 실행하세요."
        )

    with open(INSPECTION_SUMMARY_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def classify_alignment(engine_status: str, expected_result: str) -> str:
    """
    프로그램 판정과 사람 기준 expected_result를 비교한다.

    중요한 순서:
    - DANGEROUS_FALSE_PASS: 사람 기준 FAIL인데 프로그램 PASS
    - FALSE_FAIL: 사람 기준 PASS인데 프로그램 FAIL
    - OVER_REVIEW: 사람 기준 PASS/FAIL인데 프로그램 REVIEW
    - OVER_CONFIDENT: 사람 기준 REVIEW인데 프로그램이 PASS/FAIL 확정
    """

    engine_status = (engine_status or "").strip().upper()
    expected_result = (expected_result or "").strip().upper()

    if expected_result in {"", "UNKNOWN"}:
        return "UNLABELLED"

    if engine_status == expected_result:
        return "MATCH"

    if engine_status == "PASS" and expected_result == "FAIL":
        return "DANGEROUS_FALSE_PASS"

    if engine_status == "FAIL" and expected_result == "PASS":
        return "FALSE_FAIL"

    if engine_status == "REVIEW" and expected_result in {"PASS", "FAIL"}:
        return "OVER_REVIEW"

    if engine_status in {"PASS", "FAIL"} and expected_result == "REVIEW":
        return "OVER_CONFIDENT"

    return "MISMATCH"


def get_issue_priority(alignment_type: str) -> int:
    """
    사람이 먼저 봐야 하는 문제 순서.
    """

    priority_map = {
        "DANGEROUS_FALSE_PASS": 1,
        "FALSE_FAIL": 2,
        "OVER_CONFIDENT": 3,
        "MISMATCH": 4,
        "OVER_REVIEW": 5,
        "UNLABELLED": 6,
        "MATCH": 9,
    }

    return priority_map.get(alignment_type, 99)


def write_csv(path: Path, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        return

    fieldnames = list(rows[0].keys())

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# Analysis
# ============================================================


def analyze_results():
    rows = load_inspection_summary()

    enriched_rows = []

    basic_counter = Counter()
    expected_counter = Counter()
    alignment_counter = Counter()

    category_status = defaultdict(lambda: Counter())
    category_expected = defaultdict(lambda: Counter())
    category_alignment = defaultdict(lambda: Counter())

    reason_counter = Counter()

    for row in rows:
        final_status = row.get("final_status", "").strip().upper()
        expected_result = row.get("expected_result", "").strip().upper()
        category = row.get("category", "UNKNOWN").strip() or "UNKNOWN"
        final_reasons = row.get("final_reasons", "")

        alignment_type = classify_alignment(final_status, expected_result)

        row["alignment_type"] = alignment_type
        row["issue_priority"] = get_issue_priority(alignment_type)

        enriched_rows.append(row)

        basic_counter[final_status] += 1
        expected_counter[expected_result] += 1
        alignment_counter[alignment_type] += 1

        category_status[category][final_status] += 1
        category_expected[category][expected_result] += 1
        category_alignment[category][alignment_type] += 1

        if final_status == "FAIL":
            reason_counter[final_reasons] += 1

    # 사람이 봐야 하는 목록:
    # 1. 프로그램이 REVIEW/FAIL로 판정한 것
    # 2. 사람 기준과 불일치한 것
    # 3. 특히 위험한 false pass
    issue_rows = []

    for row in enriched_rows:
        final_status = row.get("final_status", "").strip().upper()
        alignment_type = row.get("alignment_type", "")

        if final_status in {"REVIEW", "FAIL"} or alignment_type != "MATCH":
            issue_rows.append(row)

    issue_rows = sorted(
        issue_rows,
        key=lambda r: (
            int(r.get("issue_priority", 99)),
            r.get("category", ""),
            r.get("file_name", ""),
        ),
    )

    # 카테고리별 요약
    category_summary_rows = []

    for category in sorted(category_status.keys()):
        status_counter = category_status[category]
        expected_counter_by_category = category_expected[category]
        alignment_counter_by_category = category_alignment[category]

        category_summary_rows.append(
            {
                "category": category,
                "total": sum(status_counter.values()),
                "engine_PASS": status_counter.get("PASS", 0),
                "engine_REVIEW": status_counter.get("REVIEW", 0),
                "engine_FAIL": status_counter.get("FAIL", 0),
                "expected_PASS": expected_counter_by_category.get("PASS", 0),
                "expected_REVIEW": expected_counter_by_category.get("REVIEW", 0),
                "expected_FAIL": expected_counter_by_category.get("FAIL", 0),
                "MATCH": alignment_counter_by_category.get("MATCH", 0),
                "DANGEROUS_FALSE_PASS": alignment_counter_by_category.get(
                    "DANGEROUS_FALSE_PASS", 0
                ),
                "FALSE_FAIL": alignment_counter_by_category.get("FALSE_FAIL", 0),
                "OVER_REVIEW": alignment_counter_by_category.get("OVER_REVIEW", 0),
                "OVER_CONFIDENT": alignment_counter_by_category.get(
                    "OVER_CONFIDENT", 0
                ),
                "MISMATCH": alignment_counter_by_category.get("MISMATCH", 0),
                "UNLABELLED": alignment_counter_by_category.get("UNLABELLED", 0),
            }
        )

    write_csv(FAIL_REVIEW_LIST_PATH, issue_rows)
    write_csv(CATEGORY_STATUS_SUMMARY_PATH, category_summary_rows)

    print_basic_summary(rows, basic_counter, expected_counter)
    print_category_status_summary(category_summary_rows)
    print_alignment_summary(alignment_counter)
    print_fail_reason_summary(reason_counter)

    print("\n========== SAVED FILES ==========")
    print(f"Saved issue list       : {FAIL_REVIEW_LIST_PATH}")
    print(f"Saved category summary : {CATEGORY_STATUS_SUMMARY_PATH}")
    print("=================================")


def print_basic_summary(rows, basic_counter, expected_counter):
    print("\n========== BASIC SUMMARY ==========")
    print(f"Total items : {len(rows)}")
    print("-----------------------------------")
    print("[Engine Result]")
    print(f"PASS   : {basic_counter.get('PASS', 0)}")
    print(f"REVIEW : {basic_counter.get('REVIEW', 0)}")
    print(f"FAIL   : {basic_counter.get('FAIL', 0)}")
    print("-----------------------------------")
    print("[Human Expected Result]")
    print(f"PASS   : {expected_counter.get('PASS', 0)}")
    print(f"REVIEW : {expected_counter.get('REVIEW', 0)}")
    print(f"FAIL   : {expected_counter.get('FAIL', 0)}")
    print(f"UNKNOWN: {expected_counter.get('UNKNOWN', 0)}")
    print("===================================")


def print_category_status_summary(category_summary_rows):
    print("\n========== CATEGORY x STATUS ==========")

    for row in category_summary_rows:
        print(
            f"{row['category']:16s} | "
            f"Engine P/R/F = {row['engine_PASS']:2d}/{row['engine_REVIEW']:2d}/{row['engine_FAIL']:2d} | "
            f"Expected P/R/F = {row['expected_PASS']:2d}/{row['expected_REVIEW']:2d}/{row['expected_FAIL']:2d}"
        )

    print("=======================================")


def print_alignment_summary(alignment_counter):
    print("\n========== HUMAN ALIGNMENT SUMMARY ==========")

    keys = [
        "MATCH",
        "DANGEROUS_FALSE_PASS",
        "FALSE_FAIL",
        "OVER_REVIEW",
        "OVER_CONFIDENT",
        "MISMATCH",
        "UNLABELLED",
    ]

    for key in keys:
        print(f"{key:22s}: {alignment_counter.get(key, 0)}")

    print("---------------------------------------------")

    dangerous = alignment_counter.get("DANGEROUS_FALSE_PASS", 0)
    false_fail = alignment_counter.get("FALSE_FAIL", 0)
    over_review = alignment_counter.get("OVER_REVIEW", 0)

    if dangerous > 0:
        print("주의: DANGEROUS_FALSE_PASS가 있습니다.")
        print(
            "→ 사람 기준 FAIL인데 프로그램이 PASS로 보낸 항목입니다. 가장 먼저 수정해야 합니다."
        )

    if false_fail > 0:
        print("주의: FALSE_FAIL이 있습니다.")
        print(
            "→ 사람 기준 PASS인데 프로그램이 FAIL로 보낸 항목입니다. 과검출 가능성이 있습니다."
        )

    if over_review > 0:
        print("참고: OVER_REVIEW가 있습니다.")
        print(
            "→ 사람 기준 PASS/FAIL로 정할 수 있는데 프로그램이 REVIEW로 보낸 항목입니다."
        )

    print("=============================================")


def print_fail_reason_summary(reason_counter):
    print("\n========== FAIL REASON SUMMARY ==========")

    if not reason_counter:
        print("FAIL reason 없음")
        print("=========================================")
        return

    for reason, count in reason_counter.most_common(20):
        print(f"{count}개 | {reason}")

    print("=========================================")


# ============================================================
# Main
# ============================================================


def main():
    analyze_results()


if __name__ == "__main__":
    main()
