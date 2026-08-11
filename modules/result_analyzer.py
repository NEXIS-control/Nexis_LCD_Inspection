import csv
from collections import Counter, defaultdict
from pathlib import Path

try:
    from modules.path_config import RESULTS_DIR
except ModuleNotFoundError:
    from path_config import RESULTS_DIR


INSPECTION_SUMMARY_CSV_PATH = RESULTS_DIR / "inspection_summary.csv"
FAIL_LIST_PATH = RESULTS_DIR / "fail_list.csv"
CATEGORY_STATUS_SUMMARY_PATH = RESULTS_DIR / "category_status_summary.csv"


def load_inspection_summary():
    if not INSPECTION_SUMMARY_CSV_PATH.exists():
        raise FileNotFoundError(
            f"inspection_summary.csv 파일이 없습니다: {INSPECTION_SUMMARY_CSV_PATH}\n"
            "먼저 python modules/decision_engine.py 를 실행하세요."
        )

    with open(INSPECTION_SUMMARY_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def expected_to_binary(expected_result: str) -> str:
    expected = (expected_result or "").strip().upper()
    if expected == "PASS":
        return "PASS"
    if expected in {"REVIEW", "FAIL"}:
        return "FAIL"
    return "UNKNOWN"


def classify_alignment(engine_status: str, expected_binary_result: str) -> str:
    engine = (engine_status or "").strip().upper()
    expected = (expected_binary_result or "").strip().upper()

    if expected not in {"PASS", "FAIL"}:
        return "UNLABELLED"
    if engine == expected:
        return "MATCH"
    if engine == "PASS" and expected == "FAIL":
        return "DANGEROUS_FALSE_PASS"
    if engine == "FAIL" and expected == "PASS":
        return "FALSE_FAIL"
    return "MISMATCH"


def issue_priority(alignment_type: str, final_status: str) -> int:
    if alignment_type == "DANGEROUS_FALSE_PASS":
        return 1
    if alignment_type == "FALSE_FAIL":
        return 2
    if alignment_type not in {"MATCH", "UNLABELLED"}:
        return 3
    if final_status == "FAIL":
        return 4
    if alignment_type == "UNLABELLED":
        return 8
    return 9


def write_csv(path: Path, rows: list, fieldnames=None):
    path.parent.mkdir(parents=True, exist_ok=True)

    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        if fieldnames:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def analyze_results():
    rows = load_inspection_summary()

    engine_counter = Counter()
    original_expected_counter = Counter()
    binary_expected_counter = Counter()
    alignment_counter = Counter()
    category_engine = defaultdict(Counter)
    category_expected = defaultdict(Counter)
    category_alignment = defaultdict(Counter)
    enriched_rows = []

    for row in rows:
        final_status = row.get("final_status", "").strip().upper()
        original_expected = row.get("expected_result", "").strip().upper()
        binary_expected = row.get(
            "expected_binary_result", ""
        ).strip().upper() or expected_to_binary(original_expected)
        category = row.get("category", "UNKNOWN").strip() or "UNKNOWN"
        alignment_type = classify_alignment(final_status, binary_expected)

        row["expected_binary_result"] = binary_expected
        row["alignment_type"] = alignment_type
        row["issue_priority"] = issue_priority(alignment_type, final_status)
        enriched_rows.append(row)

        engine_counter[final_status] += 1
        original_expected_counter[original_expected] += 1
        binary_expected_counter[binary_expected] += 1
        alignment_counter[alignment_type] += 1
        category_engine[category][final_status] += 1
        category_expected[category][binary_expected] += 1
        category_alignment[category][alignment_type] += 1

    fail_rows = [
        row
        for row in enriched_rows
        if row.get("final_status") == "FAIL" or row.get("alignment_type") != "MATCH"
    ]
    fail_rows.sort(
        key=lambda row: (
            int(row.get("issue_priority", 99)),
            row.get("category", ""),
            row.get("file_name", ""),
        )
    )

    category_rows = []
    for category in sorted(category_engine):
        engine = category_engine[category]
        expected = category_expected[category]
        alignment = category_alignment[category]
        category_rows.append(
            {
                "category": category,
                "total": sum(engine.values()),
                "engine_PASS": engine.get("PASS", 0),
                "engine_FAIL": engine.get("FAIL", 0),
                "expected_binary_PASS": expected.get("PASS", 0),
                "expected_binary_FAIL": expected.get("FAIL", 0),
                "MATCH": alignment.get("MATCH", 0),
                "DANGEROUS_FALSE_PASS": alignment.get("DANGEROUS_FALSE_PASS", 0),
                "FALSE_FAIL": alignment.get("FALSE_FAIL", 0),
                "MISMATCH": alignment.get("MISMATCH", 0),
                "UNLABELLED": alignment.get("UNLABELLED", 0),
            }
        )

    write_csv(
        FAIL_LIST_PATH,
        fail_rows,
        fieldnames=list(enriched_rows[0].keys()) if enriched_rows else [],
    )
    write_csv(
        CATEGORY_STATUS_SUMMARY_PATH,
        category_rows,
        fieldnames=list(category_rows[0].keys()) if category_rows else [],
    )

    true_fail = sum(
        1
        for row in enriched_rows
        if row["final_status"] == "FAIL" and row["expected_binary_result"] == "FAIL"
    )
    true_pass = sum(
        1
        for row in enriched_rows
        if row["final_status"] == "PASS" and row["expected_binary_result"] == "PASS"
    )
    false_fail = alignment_counter.get("FALSE_FAIL", 0)
    false_pass = alignment_counter.get("DANGEROUS_FALSE_PASS", 0)
    labelled_count = true_fail + true_pass + false_fail + false_pass

    metrics = {
        "accuracy": safe_rate(true_fail + true_pass, labelled_count),
        "fail_recall": safe_rate(true_fail, true_fail + false_pass),
        "fail_precision": safe_rate(true_fail, true_fail + false_fail),
        "pass_recall": safe_rate(true_pass, true_pass + false_fail),
    }

    print("\n========== BINARY RESULT SUMMARY ==========")
    print(f"Total items : {len(rows)}")
    print(f"PASS        : {engine_counter.get('PASS', 0)}")
    print(f"FAIL        : {engine_counter.get('FAIL', 0)}")
    print("-------------------------------------------")
    print("[Original human labels]")
    print(f"PASS        : {original_expected_counter.get('PASS', 0)}")
    print(f"REVIEW      : {original_expected_counter.get('REVIEW', 0)}")
    print(f"FAIL        : {original_expected_counter.get('FAIL', 0)}")
    print("[Binary expected: original REVIEW -> FAIL]")
    print(f"PASS        : {binary_expected_counter.get('PASS', 0)}")
    print(f"FAIL        : {binary_expected_counter.get('FAIL', 0)}")
    print("===========================================")

    print("\n========== BINARY CONFUSION MATRIX ==========")
    print(f"True PASS            : {true_pass}")
    print(f"True FAIL            : {true_fail}")
    print(f"DANGEROUS FALSE PASS : {false_pass}")
    print(f"FALSE FAIL           : {false_fail}")
    print("---------------------------------------------")
    print(f"Accuracy       : {metrics['accuracy'] * 100:.2f}%")
    print(f"FAIL recall    : {metrics['fail_recall'] * 100:.2f}%")
    print(f"FAIL precision : {metrics['fail_precision'] * 100:.2f}%")
    print(f"PASS recall    : {metrics['pass_recall'] * 100:.2f}%")
    print("=============================================")

    print("\n========== CATEGORY x BINARY STATUS ==========")
    for row in category_rows:
        print(
            f"{row['category']:16s} | "
            f"Engine P/F={row['engine_PASS']:2d}/{row['engine_FAIL']:2d} | "
            f"Expected P/F={row['expected_binary_PASS']:2d}/"
            f"{row['expected_binary_FAIL']:2d}"
        )
    print("==============================================")

    print("\n========== SAVED FILES ==========")
    print(f"Saved FAIL list        : {FAIL_LIST_PATH}")
    print(f"Saved category summary : {CATEGORY_STATUS_SUMMARY_PATH}")
    print("=================================")


def main():
    analyze_results()


if __name__ == "__main__":
    main()
