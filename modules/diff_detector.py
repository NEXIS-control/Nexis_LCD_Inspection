import csv
import json
from pathlib import Path

import cv2
import numpy as np

# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        PROJECT_ROOT,
        RESOLVED_MATCHES_PATH,
        DETECTED_ROIS_PATH,
        REFERENCE_REGISTRY_PATH,
        INSPECTION_PROFILES_PATH,
        RESULTS_DIR,
    )
except ModuleNotFoundError:
    from path_config import (
        PROJECT_ROOT,
        RESOLVED_MATCHES_PATH,
        DETECTED_ROIS_PATH,
        REFERENCE_REGISTRY_PATH,
        INSPECTION_PROFILES_PATH,
        RESULTS_DIR,
    )


# ============================================================
# Unicode-safe OpenCV Image IO
# ============================================================


def read_image(image_path: Path):
    """
    Windows 한글 경로에서도 안전하게 이미지를 읽기 위한 함수.
    cv2.imread는 한글 경로에서 실패할 수 있어서 np.fromfile + cv2.imdecode 사용.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

    data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

    return image


def save_image(image_path: Path, image):
    """
    Windows 한글 경로에서도 안전하게 이미지를 저장하기 위한 함수.
    """
    image_path = Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)

    ext = image_path.suffix
    success, encoded = cv2.imencode(ext, image)

    if not success:
        raise ValueError(f"이미지 인코딩 실패: {image_path}")

    encoded.tofile(str(image_path))


# ============================================================
# Config Loaders
# ============================================================


def load_resolved_matches():
    """
    results/resolved_matches.json 파일을 읽는다.
    이 파일은 pair_manager.py가 생성한 reference/capture 매칭 결과이다.
    """
    if not RESOLVED_MATCHES_PATH.exists():
        raise FileNotFoundError(
            f"{RESOLVED_MATCHES_PATH} 파일이 없습니다. "
            "먼저 python modules/pair_manager.py를 실행하세요."
        )

    with open(RESOLVED_MATCHES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_registry():
    """
    config/reference_registry.csv 파일을 읽어서
    file_name 기준으로 category/profile 정보를 가져온다.
    """
    if not REFERENCE_REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"{REFERENCE_REGISTRY_PATH} 파일이 없습니다. "
            "먼저 reference_registry.csv를 생성하세요."
        )

    registry = {}

    with open(REFERENCE_REGISTRY_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            file_name = row.get("file_name", "").strip()

            if file_name:
                registry[file_name] = row

    return registry


def load_inspection_profiles():
    """
    config/inspection_profiles.json 파일을 읽는다.
    카테고리별 diff_threshold, min_diff_area 등을 가져온다.
    """
    if not INSPECTION_PROFILES_PATH.exists():
        raise FileNotFoundError(
            f"{INSPECTION_PROFILES_PATH} 파일이 없습니다. "
            "먼저 inspection_profiles.json을 생성하세요."
        )

    with open(INSPECTION_PROFILES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Utility
# ============================================================


def to_abs_path(relative_path: str) -> Path:
    """
    JSON/CSV에 저장된 프로젝트 기준 상대 경로를 실제 절대 경로로 변환한다.
    예:
    data/reference/14-33.png
    → C:/Users/.../Nexis_LCD_Inspection/data/reference/14-33.png
    """
    return PROJECT_ROOT / relative_path


def to_project_relative_path(path: Path) -> str:
    """
    절대 경로를 프로젝트 기준 상대 경로로 변환한다.
    JSON에는 Windows \\ 대신 / 형태로 저장한다.
    """
    return path.relative_to(PROJECT_ROOT).as_posix()


def ensure_same_size(reference_img, capture_img):
    """
    reference와 capture 이미지 크기를 맞춘다.
    원칙적으로는 두 이미지 크기가 같아야 한다.
    만약 다르면 capture를 reference 크기에 맞춰 resize한다.
    """
    ref_h, ref_w = reference_img.shape[:2]
    cap_h, cap_w = capture_img.shape[:2]

    if (ref_h, ref_w) == (cap_h, cap_w):
        return capture_img, False

    resized_capture = cv2.resize(
        capture_img, (ref_w, ref_h), interpolation=cv2.INTER_AREA
    )
    return resized_capture, True


def make_debug_canvas(reference_img, capture_img, diff_mask, rois, title_text):
    """
    확인용 debug 이미지를 만든다.
    왼쪽: reference
    가운데: capture + 차이 영역 박스
    오른쪽: diff mask
    """

    ref_vis = reference_img.copy()
    cap_vis = capture_img.copy()

    # 차이 영역 bbox 표시
    for roi in rois:
        x, y, w, h = roi["bbox"]
        roi_id = roi["roi_id"]

        cv2.rectangle(cap_vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(
            cap_vis,
            roi_id,
            (x, max(y - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    mask_vis = cv2.cvtColor(diff_mask, cv2.COLOR_GRAY2BGR)

    # 상단 텍스트 영역 추가
    header_height = 40
    h, w = reference_img.shape[:2]

    def add_header(img, text):
        canvas = np.full((h + header_height, w, 3), 255, dtype=np.uint8)
        canvas[header_height:, :] = img
        cv2.putText(
            canvas,
            text,
            (15, 27),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        return canvas

    ref_vis = add_header(ref_vis, "REFERENCE")
    cap_vis = add_header(cap_vis, "CAPTURE + DIFF ROIS")
    mask_vis = add_header(mask_vis, "DIFF MASK")

    debug_canvas = cv2.hconcat([ref_vis, cap_vis, mask_vis])

    # 전체 제목 추가
    total_h, total_w = debug_canvas.shape[:2]
    final_header = 45
    final_canvas = np.full((total_h + final_header, total_w, 3), 255, dtype=np.uint8)
    final_canvas[final_header:, :] = debug_canvas

    cv2.putText(
        final_canvas,
        title_text,
        (20, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )

    return final_canvas


# ============================================================
# Diff Detection Core
# ============================================================


def detect_diff_rois(
    reference_img,
    capture_img,
    diff_threshold: int = 30,
    min_diff_area: int = 150,
    merge_distance: int = 15,
):
    """
    reference와 capture 이미지를 비교해서 차이 영역 ROI를 검출한다.

    처리 흐름:
    1. grayscale 변환
    2. blur로 작은 노이즈 완화
    3. absdiff로 픽셀 차이 계산
    4. threshold로 차이가 큰 픽셀만 추출
    5. morphology로 근처 차이들을 묶음
    6. contour 검출
    7. bbox 생성
    """

    # 1. grayscale
    ref_gray = cv2.cvtColor(reference_img, cv2.COLOR_BGR2GRAY)
    cap_gray = cv2.cvtColor(capture_img, cv2.COLOR_BGR2GRAY)

    # 2. blur
    ref_blur = cv2.GaussianBlur(ref_gray, (3, 3), 0)
    cap_blur = cv2.GaussianBlur(cap_gray, (3, 3), 0)

    # 3. absolute difference
    diff = cv2.absdiff(ref_blur, cap_blur)

    # 4. threshold
    _, raw_mask = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)

    # 5. morphology
    # 작은 점 제거
    open_kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, open_kernel)

    # 가까운 차이 영역 묶기
    merge_kernel_size = max(3, int(merge_distance))
    merge_kernel = np.ones((merge_kernel_size, merge_kernel_size), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, merge_kernel)

    # 6. contour
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_h, image_w = reference_img.shape[:2]
    image_area = image_h * image_w

    rois = []

    for idx, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)

        # bbox 내부의 실제 차이 픽셀 수 계산
        roi_raw_mask = raw_mask[y : y + h, x : x + w]
        diff_pixel_area = int(cv2.countNonZero(roi_raw_mask))

        bbox_area = int(w * h)
        contour_area = float(cv2.contourArea(contour))

        # 너무 작은 차이는 무시
        if max(diff_pixel_area, contour_area) < min_diff_area:
            continue

        area_ratio = diff_pixel_area / image_area

        rois.append(
            {
                "roi_id": f"diff_{len(rois) + 1:03d}",
                "bbox": [int(x), int(y), int(w), int(h)],
                "diff_pixel_area": int(diff_pixel_area),
                "bbox_area": int(bbox_area),
                "area_ratio": round(float(area_ratio), 6),
            }
        )

    # 위쪽에서 아래쪽, 왼쪽에서 오른쪽 순서로 정렬
    rois = sorted(rois, key=lambda r: (r["bbox"][1], r["bbox"][0]))

    # 정렬 후 roi_id 다시 부여
    for idx, roi in enumerate(rois):
        roi["roi_id"] = f"diff_{idx + 1:03d}"

    total_diff_area = int(sum(roi["diff_pixel_area"] for roi in rois))
    total_diff_area_ratio = round(total_diff_area / image_area, 6)

    return {
        "rois": rois,
        "raw_mask": raw_mask,
        "processed_mask": mask,
        "total_diff_area": total_diff_area,
        "total_diff_area_ratio": total_diff_area_ratio,
    }


# ============================================================
# Main Processing
# ============================================================


def process_one_pair(file_name, match_info, registry_info, profile_info):
    """
    이미지 한 쌍에 대해 diff ROI 검출을 수행한다.
    """

    screen_id = match_info.get("screen_id", Path(file_name).stem)

    reference_path = to_abs_path(match_info["reference_image"])
    capture_path = to_abs_path(match_info["capture_image"])

    reference_img = read_image(reference_path)
    capture_img = read_image(capture_path)

    capture_img, resized = ensure_same_size(reference_img, capture_img)

    diff_threshold = int(profile_info.get("diff_threshold", 30))
    min_diff_area = int(profile_info.get("min_diff_area", 150))
    merge_distance = int(profile_info.get("merge_distance", 15))

    diff_result = detect_diff_rois(
        reference_img=reference_img,
        capture_img=capture_img,
        diff_threshold=diff_threshold,
        min_diff_area=min_diff_area,
        merge_distance=merge_distance,
    )

    rois = diff_result["rois"]

    category = registry_info.get("category", "general_diff")
    profile = registry_info.get("profile", "general_diff_profile")

    debug_dir = RESULTS_DIR / "diff_debug"
    debug_path = debug_dir / f"{screen_id}_diff.jpg"

    title_text = (
        f"{file_name} | category={category} | profile={profile} | "
        f"rois={len(rois)} | area_ratio={diff_result['total_diff_area_ratio']}"
    )

    debug_canvas = make_debug_canvas(
        reference_img=reference_img,
        capture_img=capture_img,
        diff_mask=diff_result["processed_mask"],
        rois=rois,
        title_text=title_text,
    )

    save_image(debug_path, debug_canvas)

    image_h, image_w = reference_img.shape[:2]

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": category,
        "profile": profile,
        "reference_image": match_info["reference_image"],
        "capture_image": match_info["capture_image"],
        "image_width": int(image_w),
        "image_height": int(image_h),
        "capture_resized_to_reference": resized,
        "diff_threshold": diff_threshold,
        "min_diff_area": min_diff_area,
        "merge_distance": merge_distance,
        "diff_roi_count": len(rois),
        "total_diff_area": diff_result["total_diff_area"],
        "total_diff_area_ratio": diff_result["total_diff_area_ratio"],
        "rois": rois,
        "debug_image": to_project_relative_path(debug_path),
    }


def run_diff_detection():
    """
    전체 73쌍에 대해 diff ROI 검출을 수행한다.
    """

    resolved_matches = load_resolved_matches()
    registry = load_reference_registry()
    profiles_json = load_inspection_profiles()

    profiles = profiles_json.get("profiles", {})
    matches = resolved_matches.get("matches", {})

    results = {}
    error_items = []

    for idx, (file_name, match_info) in enumerate(sorted(matches.items()), start=1):
        print(f"[{idx:03d}/{len(matches)}] Processing {file_name}")

        try:
            registry_info = registry.get(file_name, {})
            profile_name = registry_info.get("profile", "general_diff_profile")

            if profile_name not in profiles:
                raise KeyError(
                    f"{file_name}의 profile '{profile_name}'이 inspection_profiles.json에 없습니다."
                )

            profile_info = profiles[profile_name]

            result = process_one_pair(
                file_name=file_name,
                match_info=match_info,
                registry_info=registry_info,
                profile_info=profile_info,
            )

            results[file_name] = result

        except Exception as e:
            error_items.append(
                {
                    "file_name": file_name,
                    "error": str(e),
                }
            )
            print(f"  ERROR: {e}")

    summary = {
        "total_pairs": len(matches),
        "processed_count": len(results),
        "error_count": len(error_items),
        "total_detected_rois": sum(item["diff_roi_count"] for item in results.values()),
        "items_with_no_diff": sum(
            1 for item in results.values() if item["diff_roi_count"] == 0
        ),
        "items_with_diff": sum(
            1 for item in results.values() if item["diff_roi_count"] > 0
        ),
        "errors": error_items,
    }

    output = {
        "summary": summary,
        "results": results,
    }

    DETECTED_ROIS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(DETECTED_ROIS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


def print_summary(output):
    summary = output["summary"]

    print("\n========== DIFF DETECTOR SUMMARY ==========")
    print(f"Total pairs        : {summary['total_pairs']}")
    print(f"Processed count    : {summary['processed_count']}")
    print(f"Error count        : {summary['error_count']}")
    print(f"Items with diff    : {summary['items_with_diff']}")
    print(f"Items with no diff : {summary['items_with_no_diff']}")
    print(f"Total diff ROIs    : {summary['total_detected_rois']}")
    print("-------------------------------------------")
    print(f"Saved JSON         : {DETECTED_ROIS_PATH}")
    print(f"Debug images       : {RESULTS_DIR / 'diff_debug'}")
    print("===========================================")


def main():
    output = run_diff_detection()
    print_summary(output)


if __name__ == "__main__":
    main()
