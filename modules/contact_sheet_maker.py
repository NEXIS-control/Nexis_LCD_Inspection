from math import ceil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        RESULTS_DIR,
        REFERENCE_CONTACT_SHEET_PATH,
        get_reference_images,
    )
except ModuleNotFoundError:
    from path_config import (
        RESULTS_DIR,
        REFERENCE_CONTACT_SHEET_PATH,
        get_reference_images,
    )


# ============================================================
# Font
# ============================================================


def get_font(size: int = 18):
    """
    썸네일 아래에 파일명을 표시하기 위한 폰트를 불러온다.
    Arial이 없으면 PIL 기본 폰트를 사용한다.
    """
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


# ============================================================
# Contact Sheet Maker
# ============================================================


def make_contact_sheet(
    image_paths,
    output_path: Path,
    columns: int = 4,
    thumb_width: int = 320,
    thumb_height: int = 120,
    label_height: int = 35,
    padding: int = 20,
):
    """
    reference 이미지들을 썸네일 표 형태로 저장한다.

    Parameters
    ----------
    image_paths:
        reference 이미지 경로 목록

    output_path:
        저장할 contact sheet 이미지 경로

    columns:
        한 줄에 배치할 이미지 개수

    thumb_width, thumb_height:
        썸네일 이미지 크기

    label_height:
        파일명 표시 영역 높이

    padding:
        셀 사이 여백
    """

    if not image_paths:
        raise ValueError(
            "reference 이미지가 없습니다. data/reference 폴더를 확인하세요."
        )

    rows = ceil(len(image_paths) / columns)

    cell_width = thumb_width + padding
    cell_height = thumb_height + label_height + padding

    sheet_width = columns * cell_width + padding
    sheet_height = rows * cell_height + padding

    contact_sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
    draw = ImageDraw.Draw(contact_sheet)
    font = get_font(size=18)

    for idx, image_path in enumerate(image_paths):
        row = idx // columns
        col = idx % columns

        x = padding + col * cell_width
        y = padding + row * cell_height

        # 이미지 열기
        img = Image.open(image_path).convert("RGB")

        # 원본 비율 유지하면서 썸네일로 축소
        img.thumbnail((thumb_width, thumb_height))

        # 썸네일을 셀 중앙에 배치
        thumb_x = x + (thumb_width - img.width) // 2
        thumb_y = y

        contact_sheet.paste(img, (thumb_x, thumb_y))

        # 이미지 테두리
        draw.rectangle(
            [x, y, x + thumb_width, y + thumb_height],
            outline="black",
            width=1,
        )

        # 파일명 표시
        label_text = f"{idx + 1:02d}. {image_path.name}"
        label_x = x
        label_y = y + thumb_height + 8

        draw.text((label_x, label_y), label_text, fill="black", font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet.save(output_path, quality=95)


# ============================================================
# Main
# ============================================================


def main():
    reference_images = get_reference_images()

    print("========== CONTACT SHEET MAKER ==========")
    print(f"Reference image count: {len(reference_images)}")

    make_contact_sheet(
        image_paths=reference_images,
        output_path=REFERENCE_CONTACT_SHEET_PATH,
        columns=2,
        thumb_width=640,
        thumb_height=240,
        label_height=45,
        padding=25,
    )

    print(f"Saved to: {REFERENCE_CONTACT_SHEET_PATH}")
    print("=========================================")


if __name__ == "__main__":
    main()
