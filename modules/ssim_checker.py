import json
from pathlib import Path

import cv2
import numpy as np
from skimage.metrics import structural_similarity as compare_ssim


# ============================================================
# Import path_config
# ============================================================

try:
    from modules.path_config import (
        PROJECT_ROOT,
        DETECTED_ROIS_PATH,
        RESULTS_DIR,
    )
except ModuleNotFoundError:
    from path_config import (
        PROJECT_ROOT,
        DETECTED_ROIS_PATH,
        RESULTS_DIR,
    )


# ============================================================
# Output Paths
# ============================================================

SSIM_RESULTS_PATH = RESULTS_DIR / "ssim_results.json"
SSIM_DEBUG_DIR = RESULTS_DIR / "ssim_debug"


# ============================================================
# Unicode-safe OpenCV Image IO
# ============================================================

def read_image(image_path: Path):
    """
    Windows 한글 경로에서도 안전하게 이미지를 읽기 위한 함수.
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
# Utility
# ============================================================

def to_abs_path(relative_path: str) -> Path:
    """
    프로젝트 기준 상대 경로를 절대 경로로 변환한다.
    """
    return PROJECT_ROOT / relative_path


def to_project_relative_path(path: Path) -> str:
    """
    절대 경로를 프로젝트 기준 상대 경로로 변환한다.
    """
    return path.relative_to(PROJECT_ROOT).as_posix()


def crop_bbox(image, bbox, padding: int = 5):
    """
    bbox 영역을 crop한다.
    padding을 조금 주어 주변 문맥까지 포함한다.

    bbox = [x, y, w, h]
    """
    x, y, w, h = bbox

    img_h, img_w = image.shape[:2]

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)

    crop = image[y1:y2, x1:x2]

    return crop, [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]


def ensure_same_size(reference_crop, capture_crop):
    """
    SSIM 계산을 위해 두 crop 크기를 맞춘다.
    """
    ref_h, ref_w = reference_crop.shape[:2]
    cap_h, cap_w = capture_crop.shape[:2]

    if (ref_h, ref_w) == (cap_h, cap_w):
        return capture_crop, False

    resized_capture = cv2.resize(
        capture_crop,
        (ref_w, ref_h),
        interpolation=cv2.INTER_AREA,
    )

    return resized_capture, True


def compute_ssim_score(reference_crop, capture_crop):
    """
    reference crop과 capture crop의 SSIM 점수를 계산한다.
    """
    if reference_crop.size == 0 or capture_crop.size == 0:
        return None

    capture_crop, resized = ensure_same_size(reference_crop, capture_crop)

    ref_gray = cv2.cvtColor(reference_crop, cv2.COLOR_BGR2GRAY)
    cap_gray = cv2.cvtColor(capture_crop, cv2.COLOR_BGR2GRAY)

    score, diff_map = compare_ssim(
        ref_gray,
        cap_gray,
        full=True,
        data_range=255,
    )

    return {
        "ssim_score": round(float(score), 6),
        "capture_resized_to_reference": resized,
    }


def classify_ssim(score, ssim_pass: float, ssim_review: float):
    """
    SSIM 점수를 PASS / REVIEW / FAIL 성격으로 분류한다.

    ssim_pass 이상이면 PASS
    ssim_review 이상이면 REVIEW
    그 미만이면 FAIL
    """
    if score is None:
        return "REVIEW"

    if score >= ssim_pass:
        return "PASS"
    elif score >= ssim_review:
        return "REVIEW"
    else:
        return "FAIL"


def make_roi_debug_image(reference_crop, capture_crop, roi_id, ssim_score, ssim_status):
    """
    ROI별 reference/capture crop을 나란히 붙인 debug 이미지를 만든다.
    """
    capture_crop, _ = ensure_same_size(reference_crop, capture_crop)

    ref_vis = reference_crop.copy()
    cap_vis = capture_crop.copy()

    h, w = ref_vis.shape[:2]
    header_h = 45

    def add_header(img, text):
        canvas = np.full((h + header_h, w, 3), 255, dtype=np.uint8)
        canvas[header_h:, :] = img

        cv2.putText(
            canvas,
            text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

        return canvas

    ref_panel = add_header(ref_vis, "REFERENCE")
    cap_panel = add_header(cap_vis, "CAPTURE")

    combined = cv2.hconcat([ref_panel, cap_panel])

    final_header_h = 50
    total_h, total_w = combined.shape[:2]

    final_canvas = np.full((total_h + final_header_h, total_w, 3), 255, dtype=np.uint8)
    final_canvas[final_header_h:, :] = combined

    title = f"{roi_id} | SSIM={ssim_score} | {ssim_status}"

    cv2.putText(
        final_canvas,
        title,
        (15, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )

    return final_canvas


# ============================================================
# Load Detected ROIs
# ============================================================

def load_detected_rois():
    """
    diff_detector.py가 만든 results/detected_rois.json 파일을 읽는다.
    """
    if not DETECTED_ROIS_PATH.exists():
        raise FileNotFoundError(
            f"{DETECTED_ROIS_PATH} 파일이 없습니다. "
            "먼저 python modules/diff_detector.py를 실행하세요."
        )

    with open(DETECTED_ROIS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Main SSIM Logic
# ============================================================

def process_one_item(file_name, item):
    """
    한 이미지 쌍에 대해 ROI별 SSIM 검사를 수행한다.
    """
    screen_id = item["screen_id"]
    category = item["category"]
    profile = item["profile"]

    reference_path = to_abs_path(item["reference_image"])
    capture_path = to_abs_path(item["capture_image"])

    reference_img = read_image(reference_path)
    capture_img = read_image(capture_path)

    # diff_detector에서 capture resize가 있었을 수도 있으므로 여기서도 크기 맞춤
    capture_img, full_resized = ensure_same_size(reference_img, capture_img)

    ssim_pass = float(item.get("ssim_pass", 0.90))
    ssim_review = float(item.get("ssim_review", 0.75))

    # detected_rois.json에는 profile threshold가 직접 저장되어 있지 않을 수 있으므로
    # 기본값을 category 성격에 맞게 약간 보수적으로 둔다.
    if category in {"general_diff", "status_time"}:
        ssim_pass = 0.92
        ssim_review = 0.80
    elif category in {"guide_image", "popup", "card_ui", "setting_control"}:
        ssim_pass = 0.90
        ssim_review = 0.75
    elif category == "text_list":
        ssim_pass = 0.90
        ssim_review = 0.75

    roi_results = []

    for roi in item.get("rois", []):
        roi_id = roi["roi_id"]
        bbox = roi["bbox"]

        ref_crop, padded_bbox = crop_bbox(reference_img, bbox, padding=5)
        cap_crop, _ = crop_bbox(capture_img, bbox, padding=5)

        ssim_info = compute_ssim_score(ref_crop, cap_crop)

        if ssim_info is None:
            ssim_score = None
            ssim_status = "REVIEW"
            capture_resized = False
        else:
            ssim_score = ssim_info["ssim_score"]
            capture_resized = ssim_info["capture_resized_to_reference"]
            ssim_status = classify_ssim(
                score=ssim_score,
                ssim_pass=ssim_pass,
                ssim_review=ssim_review,
            )

        debug_path = SSIM_DEBUG_DIR / screen_id / f"{roi_id}_ssim.jpg"

        if ref_crop.size > 0 and cap_crop.size > 0:
            debug_image = make_roi_debug_image(
                reference_crop=ref_crop,
                capture_crop=cap_crop,
                roi_id=roi_id,
                ssim_score=ssim_score,
                ssim_status=ssim_status,
            )
            save_image(debug_path, debug_image)

        roi_result = {
            "roi_id": roi_id,
            "bbox": bbox,
            "padded_bbox": padded_bbox,
            "diff_pixel_area": roi.get("diff_pixel_area"),
            "area_ratio": roi.get("area_ratio"),
            "ssim_score": ssim_score,
            "ssim_status": ssim_status,
            "ssim_pass_threshold": ssim_pass,
            "ssim_review_threshold": ssim_review,
            "capture_crop_resized": capture_resized,
            "debug_image": to_project_relative_path(debug_path),
        }

        roi_results.append(roi_result)

    # 이미지 전체 SSIM도 참고용으로 계산
    overall_ssim_info = compute_ssim_score(reference_img, capture_img)
    overall_ssim = overall_ssim_info["ssim_score"] if overall_ssim_info else None

    fail_count = sum(1 for r in roi_results if r["ssim_status"] == "FAIL")
    review_count = sum(1 for r in roi_results if r["ssim_status"] == "REVIEW")
    pass_count = sum(1 for r in roi_results if r["ssim_status"] == "PASS")

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": category,
        "profile": profile,
        "reference_image": item["reference_image"],
        "capture_image": item["capture_image"],
        "diff_roi_count": item.get("diff_roi_count", 0),
        "total_diff_area_ratio": item.get("total_diff_area_ratio"),
        "overall_ssim": overall_ssim,
        "full_capture_resized_to_reference": full_resized,
        "roi_ssim_summary": {
            "pass_count": pass_count,
            "review_count": review_count,
            "fail_count": fail_count,
        },
        "roi_results": roi_results,
    }


def run_ssim_check():
    detected_rois = load_detected_rois()
    items = detected_rois.get("results", {})

    results = {}
    errors = []

    for idx, (file_name, item) in enumerate(sorted(items.items()), start=1):
        print(f"[{idx:03d}/{len(items)}] SSIM checking {file_name}")

        try:
            result = process_one_item(file_name, item)
            results[file_name] = result

        except Exception as e:
            errors.append({
                "file_name": file_name,
                "error": str(e),
            })
            print(f"  ERROR: {e}")

    summary = {
        "total_items": len(items),
        "processed_count": len(results),
        "error_count": len(errors),
        "items_with_roi_fail": sum(
            1 for item in results.values()
            if item["roi_ssim_summary"]["fail_count"] > 0
        ),
        "items_with_roi_review": sum(
            1 for item in results.values()
            if item["roi_ssim_summary"]["review_count"] > 0
        ),
        "items_with_no_roi": sum(
            1 for item in results.values()
            if item["diff_roi_count"] == 0
        ),
        "errors": errors,
    }

    output = {
        "summary": summary,
        "results": results,
    }

    SSIM_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(SSIM_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


def print_summary(output):
    summary = output["summary"]

    print("\n========== SSIM CHECKER SUMMARY ==========")
    print(f"Total items          : {summary['total_items']}")
    print(f"Processed count      : {summary['processed_count']}")
    print(f"Error count          : {summary['error_count']}")
    print(f"Items with ROI FAIL  : {summary['items_with_roi_fail']}")
    print(f"Items with ROI REVIEW: {summary['items_with_roi_review']}")
    print(f"Items with no ROI    : {summary['items_with_no_roi']}")
    print("------------------------------------------")
    print(f"Saved JSON           : {SSIM_RESULTS_PATH}")
    print(f"Debug images         : {SSIM_DEBUG_DIR}")
    print("==========================================")


def main():
    output = run_ssim_check()
    print_summary(output)


if __name__ == "__main__":
    main()