import json
from pathlib import Path

# ============================================================
# Import path_config
# ============================================================
# 실행 방식에 따라 import 경로가 달라질 수 있어서
# 두 가지 방식을 모두 지원하도록 작성한다.
# ============================================================

try:
    from modules.path_config import (
        PROJECT_ROOT,
        REFERENCE_DIR,
        CAPTURE_DIR,
        RESULTS_DIR,
        RESOLVED_MATCHES_PATH,
        get_reference_images,
        get_capture_images,
    )
except ModuleNotFoundError:
    from path_config import (
        PROJECT_ROOT,
        REFERENCE_DIR,
        CAPTURE_DIR,
        RESULTS_DIR,
        RESOLVED_MATCHES_PATH,
        get_reference_images,
        get_capture_images,
    )


# ============================================================
# Utility
# ============================================================


def to_project_relative_path(path: Path) -> str:
    """
    절대 경로를 프로젝트 기준 상대 경로 문자열로 변환한다.
    Windows에서도 JSON에는 / 형태로 저장되게 한다.
    """
    return path.relative_to(PROJECT_ROOT).as_posix()


def get_screen_id(file_name: str) -> str:
    """
    파일명에서 확장자를 제거해 screen_id로 사용한다.
    예:
    15-14.png -> 15-14
    """
    return Path(file_name).stem


# ============================================================
# Main Matching Logic
# ============================================================


def build_filename_pairs() -> dict:
    """
    data/reference와 data/capture 폴더에서
    같은 파일명을 가진 이미지끼리 매칭한다.

    반환값:
    {
        "summary": {...},
        "matches": {...}
    }
    """

    reference_images = get_reference_images()
    capture_images = get_capture_images()

    reference_map = {p.name: p for p in reference_images}
    capture_map = {p.name: p for p in capture_images}

    reference_names = set(reference_map.keys())
    capture_names = set(capture_map.keys())

    matched_names = sorted(reference_names & capture_names)
    reference_only = sorted(reference_names - capture_names)
    capture_only = sorted(capture_names - reference_names)

    matches = {}

    for file_name in matched_names:
        reference_path = reference_map[file_name]
        capture_path = capture_map[file_name]
        screen_id = get_screen_id(file_name)

        matches[file_name] = {
            "screen_id": screen_id,
            "file_name": file_name,
            "reference_image": to_project_relative_path(reference_path),
            "capture_image": to_project_relative_path(capture_path),
            "match_mode": "filename",
            "match_status": "matched",
        }

    result = {
        "summary": {
            "reference_count": len(reference_images),
            "capture_count": len(capture_images),
            "matched_count": len(matched_names),
            "reference_only_count": len(reference_only),
            "capture_only_count": len(capture_only),
            "reference_only": reference_only,
            "capture_only": capture_only,
        },
        "matches": matches,
    }

    return result


def save_resolved_matches(result: dict) -> None:
    """
    매칭 결과를 results/resolved_matches.json에 저장한다.
    """

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with open(RESOLVED_MATCHES_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def print_matching_summary(result: dict) -> None:
    """
    매칭 결과 요약을 터미널에 출력한다.
    """

    summary = result["summary"]

    print("========== PAIR MANAGER SUMMARY ==========")
    print(f"Reference image count : {summary['reference_count']}")
    print(f"Capture image count   : {summary['capture_count']}")
    print(f"Matched pair count    : {summary['matched_count']}")
    print("------------------------------------------")
    print(f"Reference only count  : {summary['reference_only_count']}")
    print(f"Capture only count    : {summary['capture_only_count']}")

    if summary["reference_only"]:
        print("\n[Reference only files]")
        for name in summary["reference_only"]:
            print(f"- {name}")

    if summary["capture_only"]:
        print("\n[Capture only files]")
        for name in summary["capture_only"]:
            print(f"- {name}")

    print("------------------------------------------")
    print(f"Saved to: {RESOLVED_MATCHES_PATH}")
    print("==========================================")


def main():
    result = build_filename_pairs()
    save_resolved_matches(result)
    print_matching_summary(result)


if __name__ == "__main__":
    main()
