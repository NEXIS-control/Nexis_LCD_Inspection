import csv
from collections import Counter, defaultdict
from pathlib import Path

try:
    from modules.path_config import RESULTS_DIR
except ModuleNotFoundError:
    from path_config import RESULTS_DIR


INSPECTION_SUMMARY_CSV_PATH = RESULTS_DIR / "inspection_summary.csv"
FAIL_REVIEW_LIST_PATH = RESULTS_DIR / "fail_review_list.csv"
CATEGORY_STATUS_SUMMARY_PATH = RESULTS_DIR / "category_status_summary.csv"


def load_summary_rows():
    if not INSPECTION_SUMMARY_CSV_PATH.exists():
        raise FileNotFoundError(
            f"{INSPECTION_SUMMARY_CSV_PATH} 파일이 없습니다. "
            "먼저 python modules/decision_engine.py를 실행하세요."
        )

    with open(INSPECTION_SUMMARY_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def print_basic_summary(rows):
    status_counter = Counter(row["final_status"] for row in rows)
    category_counter = Counter(row["category"] for row in rows)

    print("========== BASIC SUMMARY ==========")
    print(f"Total: {len(rows)}")
    print("-----------------------------------")
    print("[Final Status]")
    for status, count in status_counter.items():
        print(f"{status}: {count}")

    print("-----------------------------------")
    print("[Category Count]")
    for category, count in category_counter.items():
        print(f"{category}: {count}")
    print("===================================")


def print_category_status_summary(rows):
    summary = defaultdict(Counter)

    for row in rows:
        category = row["category"]
        status = row["final_status"]
        summary[category][status] += 1

    print("\n========== CATEGORY x STATUS ==========")
    for category, counter in summary.items():
        pass_count = counter.get("PASS", 0)
        review_count = counter.get("REVIEW", 0)
        fail_count = counter.get("FAIL", 0)

        print(
            f"{category:18s} | "
            f"PASS {pass_count:2d} | "
            f"REVIEW {review_count:2d} | "
            f"FAIL {fail_count:2d}"
        )
    print("=======================================")

    with open(CATEGORY_STATUS_SUMMARY_PATH, "w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["category", "PASS", "REVIEW", "FAIL", "TOTAL"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for category, counter in summary.items():
            pass_count = counter.get("PASS", 0)
            review_count = counter.get("REVIEW", 0)
            fail_count = counter.get("FAIL", 0)

            writer.writerow(
                {
                    "category": category,
                    "PASS": pass_count,
                    "REVIEW": review_count,
                    "FAIL": fail_count,
                    "TOTAL": pass_count + review_count + fail_count,
                }
            )


def print_fail_reason_summary(rows):
    fail_rows = [row for row in rows if row["final_status"] == "FAIL"]
    reason_counter = Counter()

    for row in fail_rows:
        reasons = row.get("final_reasons", "")

        for reason in reasons.split("|"):
            reason = reason.strip()
            if reason:
                reason_counter[reason] += 1

    print("\n========== FAIL REASON SUMMARY ==========")
    for reason, count in reason_counter.most_common():
        print(f"{count:2d}개 | {reason}")
    print("=========================================")


def save_fail_review_list(rows):
    target_rows = [row for row in rows if row["final_status"] in {"FAIL", "REVIEW"}]

    fieldnames = [
        "file_name",
        "category",
        "profile",
        "expected_result",
        "final_status",
        "diff_roi_count",
        "review_roi_count",
        "fail_roi_count",
        "total_diff_area_ratio",
        "is_loading_like",
        "final_reasons",
        "memo",
    ]

    with open(FAIL_REVIEW_LIST_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in target_rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    print(f"\nSaved FAIL/REVIEW list: {FAIL_REVIEW_LIST_PATH}")
    print(f"Saved category summary: {CATEGORY_STATUS_SUMMARY_PATH}")


def main():
    rows = load_summary_rows()

    print_basic_summary(rows)
    print_category_status_summary(rows)
    print_fail_reason_summary(rows)
    save_fail_review_list(rows)


if __name__ == "__main__":
    main()
