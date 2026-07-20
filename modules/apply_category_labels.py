import csv
import shutil
from pathlib import Path

try:
    from modules.path_config import REFERENCE_REGISTRY_PATH
except ModuleNotFoundError:
    from path_config import REFERENCE_REGISTRY_PATH


CATEGORY_PROFILE_MAP = {
    "text_list": "text_list_profile",
    "status_time": "status_time_profile",
    "guide_image": "guide_image_profile",
    "popup": "popup_profile",
    "card_ui": "card_ui_profile",
    "setting_control": "setting_control_profile",
    "general_diff": "general_diff_profile",
}


# contact sheet 번호 순서 기준 카테고리 초안
# 주의:
# - 파일명은 업로드 이미지에서 정확히 읽기 어려워서 번호 순서 기준으로 분류함
# - 애매한 화면은 나중에 검사 결과를 보면서 수정 가능
CATEGORY_LABELS = [
    ("card_ui", "코스 카드/대시보드형 화면"),
    ("card_ui", "코스 카드/대시보드형 화면"),
    ("text_list", "여러 줄 텍스트/설정 목록 화면"),
    ("card_ui", "코스 카드/대시보드형 화면"),
    ("status_time", "시간/상태 정보 중심 화면"),
    ("setting_control", "설정값/옵션 선택 화면"),
    ("setting_control", "설정값/옵션 선택 화면"),
    ("setting_control", "설정값/옵션 선택 화면"),
    ("status_time", "진행 시간/상태바 중심 화면"),
    ("status_time", "진행 상태/텍스트 중심 화면"),
    ("status_time", "진행 상태/텍스트 중심 화면"),
    ("status_time", "진행 상태/텍스트 중심 화면"),
    ("status_time", "시간/상태 + 일부 카드 UI 화면"),
    ("status_time", "시간/상태 + 숫자 정보 화면"),
    ("card_ui", "카드형 대시보드 화면"),
    ("card_ui", "카드형 대시보드 화면"),
    ("status_time", "진행 시간/상태바 중심 화면"),
    ("status_time", "시간/상태 + 카드 UI 화면"),
    ("card_ui", "카드형 대시보드 화면"),
    ("card_ui", "카드형 대시보드 화면"),
    ("text_list", "문구/항목 선택형 화면"),
    ("text_list", "경고/알림 문구 목록 화면"),
    ("text_list", "설정값 요약/목록 화면"),
    ("setting_control", "슬라이더 조절 화면"),
    ("setting_control", "슬라이더 조절 화면"),
    ("setting_control", "슬라이더 조절 화면"),
    ("text_list", "설정값/텍스트 정보 화면"),
    ("text_list", "설정값/텍스트 정보 화면"),
    ("popup", "중앙 팝업/확인 화면"),
    ("text_list", "목록형 설정 화면"),
    ("text_list", "목록형 설정 화면"),
    ("text_list", "상세 설정/정보 목록 화면"),
    ("text_list", "아이콘 포함 목록형 화면"),
    ("text_list", "아이콘 포함 목록형 화면"),
    ("text_list", "텍스트 중심 설명/설정 화면"),
    ("guide_image", "안내 이미지 또는 설명 그림 포함 화면"),
    ("guide_image", "안내 이미지 또는 설명 그림 포함 화면"),
    ("guide_image", "안내 이미지 또는 그래프 포함 화면"),
    ("guide_image", "안내 문구/설명 이미지 화면"),
    ("text_list", "설정값/정보 목록 화면"),
    ("card_ui", "카드형 대시보드 + 숫자 정보 화면"),
    ("card_ui", "카드형 대시보드 + 숫자 정보 화면"),
    ("card_ui", "카드형 대시보드 화면"),
    ("popup", "보라색 중앙 팝업 화면"),
    ("popup", "보라색 중앙 팝업 화면"),
    ("popup", "보라색 중앙 팝업 화면"),
    ("popup", "중앙 안내 팝업 화면"),
    ("popup", "중앙 안내 팝업 화면"),
    ("popup", "로딩/처리 중 팝업 화면"),
    ("popup", "중앙 안내 팝업 화면"),
    ("popup", "로딩/처리 중 팝업 화면"),
    ("popup", "로딩/처리 중 팝업 화면"),
    ("popup", "아이콘 포함 중앙 팝업/버튼 화면"),
    ("card_ui", "코스 카드 선택 화면"),
    ("card_ui", "코스 카드 선택 화면"),
    ("card_ui", "코스 카드 선택 화면"),
    ("card_ui", "코스 카드 선택 화면"),
    ("text_list", "상세 정보/설정 목록 화면"),
    ("text_list", "상세 정보/설정 목록 화면"),
    ("setting_control", "옵션 선택/설정값 화면"),
    ("setting_control", "옵션 버튼/설정 조절 화면"),
    ("setting_control", "옵션 선택 팝업형 설정 화면"),
    ("setting_control", "설정값/옵션 선택 화면"),
    ("setting_control", "옵션 버튼 그리드 화면"),
    ("setting_control", "옵션 버튼 그리드 화면"),
    ("popup", "중앙 확인/안내 팝업 화면"),
    ("popup", "중앙 안내 팝업 화면"),
    ("card_ui", "코스 카드 선택 화면"),
    ("card_ui", "코스 카드 선택 화면"),
    ("status_time", "진행 상태/시간 문구 중심 화면"),
    ("status_time", "진행 시간/상태바 중심 화면"),
    ("status_time", "원형 진행 상태 표시 화면"),
    ("status_time", "원형 진행 상태 표시 화면"),
]


def load_rows():
    if not REFERENCE_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"{REFERENCE_REGISTRY_PATH} 파일이 없습니다. "
            "먼저 reference_registry_maker.py를 실행하세요."
        )

    with open(REFERENCE_REGISTRY_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    return rows, fieldnames


def save_rows(rows, fieldnames):
    with open(REFERENCE_REGISTRY_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows, fieldnames = load_rows()

    if len(rows) != len(CATEGORY_LABELS):
        raise ValueError(
            f"CSV 행 개수와 카테고리 라벨 개수가 다릅니다.\n"
            f"CSV rows: {len(rows)}\n"
            f"Labels  : {len(CATEGORY_LABELS)}\n"
            f"reference_registry.csv가 73개 이미지 기준인지 확인하세요."
        )

    backup_path = REFERENCE_REGISTRY_PATH.with_name("reference_registry_backup.csv")
    shutil.copy2(REFERENCE_REGISTRY_PATH, backup_path)

    for index, row in enumerate(rows):
        category, memo = CATEGORY_LABELS[index]
        profile = CATEGORY_PROFILE_MAP[category]

        row["category"] = category
        row["profile"] = profile

        # 기존 expected_result는 유지한다.
        if not row.get("expected_result", "").strip():
            row["expected_result"] = "UNKNOWN"

        # 기존 메모가 비어 있으면 자동 메모 입력
        if not row.get("memo", "").strip():
            row["memo"] = memo

    save_rows(rows, fieldnames)

    print("========== APPLY CATEGORY LABELS ==========")
    print(f"Updated file : {REFERENCE_REGISTRY_PATH}")
    print(f"Backup file  : {backup_path}")
    print(f"Updated rows : {len(rows)}")
    print("-------------------------------------------")
    print("카테고리 초안 적용 완료")
    print("애매한 이미지는 나중에 CSV에서 직접 수정하면 됩니다.")
    print("===========================================")


if __name__ == "__main__":
    main()
