import json

from modules.path_config import (
    PROJECT_ROOT,
    REFERENCE_DIR,
    CAPTURE_DIR,
    RESULTS_DIR,
    RESOLVED_MATCHES_PATH,
)

# 검사 대상으로 인정할 이미지 확장자
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg"]


def get_image_files(folder_path):
    """
    특정 폴더 안에 있는 이미지 파일 목록을 가져온다.

    반환 형식:
    {
        "14-33.png": Path(".../data/reference/14-33.png"),
        "15-65.png": Path(".../data/reference/15-65.png")
    }
    """

    image_files = {}

    for file_path in folder_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in IMAGE_EXTENSIONS:
            image_files[file_path.name] = file_path

    return image_files


def make_relative_path(file_path):
    """
    절대 경로를 프로젝트 기준 상대 경로로 바꾼다.

    예:
    C:/Users/admin/.../Nexis_LCD_Inspection/data/reference/14-33.png

    변환 후:
    data/reference/14-33.png
    """

    return file_path.relative_to(PROJECT_ROOT).as_posix()


def create_filename_matches():
    """
    reference 폴더와 capture 폴더에서 같은 파일명끼리 매칭한다.
    결과는 results/resolved_matches.json 파일로 저장한다.
    """

    # results 폴더가 없으면 자동 생성
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # reference, capture 폴더 안의 이미지 파일 목록 가져오기
    reference_files = get_image_files(REFERENCE_DIR)
    capture_files = get_image_files(CAPTURE_DIR)

    matched = {}
    unmatched_reference = []
    unmatched_capture = []

    # reference 이미지 기준으로 같은 이름의 capture 이미지가 있는지 확인
    for filename, reference_path in reference_files.items():
        if filename in capture_files:
            capture_path = capture_files[filename]
            screen_id = reference_path.stem

            matched[filename] = {
                "screen_id": screen_id,
                "reference_image": make_relative_path(reference_path),
                "capture_image": make_relative_path(capture_path),
                "match_status": "filename_matched",
            }
        else:
            unmatched_reference.append(filename)

    # capture에는 있는데 reference에는 없는 파일 확인
    for filename in capture_files:
        if filename not in reference_files:
            unmatched_capture.append(filename)

    result = {
        "matched_count": len(matched),
        "unmatched_reference": unmatched_reference,
        "unmatched_capture": unmatched_capture,
        "matches": matched,
    }

    # JSON 파일 저장
    with open(RESOLVED_MATCHES_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("===== 파일명 기반 이미지 매칭 완료 =====")
    print(f"매칭된 이미지 쌍 개수: {len(matched)}")
    print(f"reference만 있는 파일 개수: {len(unmatched_reference)}")
    print(f"capture만 있는 파일 개수: {len(unmatched_capture)}")
    print(f"저장 위치: {RESOLVED_MATCHES_PATH}")

    if unmatched_reference:
        print()
        print("[주의] reference에는 있지만 capture에는 없는 파일:")
        for filename in unmatched_reference:
            print(f"- {filename}")

    if unmatched_capture:
        print()
        print("[주의] capture에는 있지만 reference에는 없는 파일:")
        for filename in unmatched_capture:
            print(f"- {filename}")


if __name__ == "__main__":
    create_filename_matches()
