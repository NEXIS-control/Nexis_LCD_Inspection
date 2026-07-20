import csv
import json
from pathlib import Path

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        RESOLVED_MATCHES_PATH,
        REFERENCE_REGISTRY_PATH,
    )
except ModuleNotFoundError:
    from path_config import (
        RESOLVED_MATCHES_PATH,
        REFERENCE_REGISTRY_PATH,
    )


# ============================================================
# Category / Profile Mapping
# ============================================================

CATEGORY_PROFILE_MAP = {
    "text_list": "text_list_profile",
    "status_time": "status_time_profile",
    "guide_image": "guide_image_profile",
    "popup": "popup_profile",
    "card_ui": "card_ui_profile",
    "setting_control": "setting_control_profile",
    "general_diff": "general_diff_profile",
}


CSV_COLUMNS = [
    "screen_id",
    "file_name",
    "reference_image",
    "capture_image",
    "category",
    "profile",
    "expected_result",
    "memo",
]


# ============================================================
# Existing CSV Loader
# ============================================================


def load_existing_registry():
    """
    이미 reference_registry.csv가 존재하면,
    기존에 사람이 입력해둔 category/profile/memo를 보존하기 위해 읽어온다.
    """
    if not REFERENCE_REGISTRY_PATH.exists():
        return {}

    existing_rows = {}

    with open(REFERENCE_REGISTRY_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            file_name = row.get("file_name", "")
            if file_name:
                existing_rows[file_name] = row

    return existing_rows


# ============================================================
# Registry Generator
# ============================================================


def make_reference_registry():
    """
    results/resolved_matches.json을 읽어서
    config/reference_registry.csv를 생성한다.
    """

    if not RESOLVED_MATCHES_PATH.exists():
        raise FileNotFoundError(
            f"{RESOLVED_MATCHES_PATH} 파일이 없습니다. "
            "먼저 python modules/pair_manager.py를 실행하세요."
        )

    with open(RESOLVED_MATCHES_PATH, "r", encoding="utf-8") as f:
        resolved_matches = json.load(f)

    matches = resolved_matches.get("matches", {})
    existing_rows = load_existing_registry()

    rows = []

    for file_name, info in sorted(matches.items()):
        old = existing_rows.get(file_name, {})

        category = old.get("category", "").strip() or "general_diff"
        profile = old.get("profile", "").strip() or CATEGORY_PROFILE_MAP.get(
            category, "general_diff_profile"
        )

        row = {
            "screen_id": info.get("screen_id", Path(file_name).stem),
            "file_name": file_name,
            "reference_image": info.get("reference_image", ""),
            "capture_image": info.get("capture_image", ""),
            "category": category,
            "profile": profile,
            "expected_result": old.get("expected_result", "").strip() or "UNKNOWN",
            "memo": old.get("memo", "").strip(),
        }

        rows.append(row)

    REFERENCE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REFERENCE_REGISTRY_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return rows


# ============================================================
# Main
# ============================================================


def main():
    rows = make_reference_registry()

    print("========== REFERENCE REGISTRY MAKER ==========")
    print(f"Created file: {REFERENCE_REGISTRY_PATH}")
    print(f"Row count   : {len(rows)}")
    print("----------------------------------------------")
    print("Default category: general_diff")
    print("Default profile : general_diff_profile")
    print("Default expected_result: UNKNOWN")
    print("==============================================")


if __name__ == "__main__":
    main()
