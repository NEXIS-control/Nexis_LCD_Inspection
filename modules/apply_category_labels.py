import csv
from pathlib import Path

try:
    from modules.path_config import REFERENCE_REGISTRY_PATH
except ModuleNotFoundError:
    from path_config import REFERENCE_REGISTRY_PATH


# ============================================================
# Human judgement labels
# ============================================================
# 주의:
# 이 값은 decision_engine.py가 판정에 직접 사용하는 값이 아니다.
# 프로그램 결과와 사람 기준을 비교하기 위한 평가 기준이다.
# 파일명을 외워서 PASS/FAIL 시키는 용도로 사용하면 안 된다.
# ============================================================


def make_file_names(prefix: int, numbers: list[int]) -> list[str]:
    return [f"{prefix}-{number}.png" for number in numbers]


PASS_ITEMS = []
PASS_ITEMS += make_file_names(2, [8, 11, 14, 21, 30, 39, 40])
PASS_ITEMS += make_file_names(3, [1, 2, 25, 26, 27])
PASS_ITEMS += make_file_names(4, [3, 20, 43])
PASS_ITEMS += make_file_names(5, [22, 24])
PASS_ITEMS += make_file_names(7, [5, 12])
PASS_ITEMS += make_file_names(8, [1, 3, 7, 10])
PASS_ITEMS += make_file_names(11, [8, 10, 36])
PASS_ITEMS += make_file_names(12, [27, 29, 38, 94])
PASS_ITEMS += make_file_names(13, [2])
PASS_ITEMS += make_file_names(14, [3, 9, 11, 21, 23, 32])
PASS_ITEMS += make_file_names(15, [1, 12, 13, 14, 22, 27, 49, 51, 67, 150])
PASS_ITEMS += make_file_names(16, [4, 17, 19])


REVIEW_REASON_MAP = {
    "3-23.png": "중앙 사진 위치 상하 반전",
    "4-1.png": "60 C 색 희미함",
    "11-35.png": "좌측 글씨 다름",
    "13-12.png": "게이지 채워진 정도 다름",
    "14-24.png": "사진 안에 색 빠짐",
    "14-25.png": "사진 안에 색 빠짐",
    "15-4.png": "글씨 색 희미함",
    "15-62.png": "글씨 색 희미함",
    "18-3.png": "글씨는 같지만 화면 색, 게이지 위치, 글씨 전체 위치 다름",
    "18-4.png": "글씨는 같지만 화면 색, 게이지 위치, 글씨 전체 위치 다름",
    "18-5.png": "글씨는 같지만 화면 색, 게이지 위치, 글씨 전체 위치 다름",
}


FAIL_REASON_MAP = {
    "4-8.png": "상단 좌측 글씨 아예 빠짐",
    "4-9.png": "상단 좌측 글씨 아예 빠짐",
    "14-8.png": "좌측 위 그림 빠짐",
    "14-10.png": "글씨 아예 없음",
    "14-33.png": "중앙 그림 구성이 아예 다름",
    "14-34.png": "중앙 그림 구성이 아예 다름",
    "15-63.png": "좌측 그림이 아예 다름",
    "15-64.png": "좌측 그림이 아예 다름",
    "15-65.png": "좌측 그림이 아예 다름",
    "15-66.png": "좌측 그림이 아예 다름",
    "15-147.png": "상태 표시 아이콘 다름",
    "15-149.png": "글씨 구성 위치가 아예 다름",
}


def build_expected_map():
    expected_map = {}

    for file_name in PASS_ITEMS:
        expected_map[file_name] = {
            "expected_result": "PASS",
            "memo": "사람 기준 통과 가능",
        }

    for file_name, reason in REVIEW_REASON_MAP.items():
        expected_map[file_name] = {
            "expected_result": "REVIEW",
            "memo": reason,
        }

    for file_name, reason in FAIL_REASON_MAP.items():
        expected_map[file_name] = {
            "expected_result": "FAIL",
            "memo": reason,
        }

    return expected_map


def update_reference_registry():
    if not REFERENCE_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"reference_registry.csv 파일이 없습니다: {REFERENCE_REGISTRY_PATH}"
        )

    expected_map = build_expected_map()

    with open(REFERENCE_REGISTRY_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    if "expected_result" not in fieldnames:
        fieldnames.append("expected_result")

    if "memo" not in fieldnames:
        fieldnames.append("memo")

    updated_count = 0
    unknown_count = 0

    for row in rows:
        file_name = row.get("file_name", "").strip()

        if file_name in expected_map:
            row["expected_result"] = expected_map[file_name]["expected_result"]
            row["memo"] = expected_map[file_name]["memo"]
            updated_count += 1
        else:
            row["expected_result"] = "UNKNOWN"
            row["memo"] = "사람 기준표에 없음"
            unknown_count += 1

    with open(REFERENCE_REGISTRY_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    pass_count = sum(1 for row in rows if row.get("expected_result") == "PASS")
    review_count = sum(1 for row in rows if row.get("expected_result") == "REVIEW")
    fail_count = sum(1 for row in rows if row.get("expected_result") == "FAIL")

    print("\n========== HUMAN EXPECTED RESULT UPDATE ==========")
    print(f"Updated file   : {REFERENCE_REGISTRY_PATH}")
    print(f"Updated rows   : {updated_count}")
    print(f"Unknown rows   : {unknown_count}")
    print("--------------------------------------------------")
    print(f"PASS count     : {pass_count}")
    print(f"REVIEW count   : {review_count}")
    print(f"FAIL count     : {fail_count}")
    print("==================================================")


def main():
    update_reference_registry()


if __name__ == "__main__":
    main()
