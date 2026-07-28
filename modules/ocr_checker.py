import json
import re
import shutil
import unicodedata
from pathlib import Path

import cv2
import numpy as np

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

OCR_RESULTS_PATH = RESULTS_DIR / "ocr_results.json"
OCR_DEBUG_DIR = RESULTS_DIR / "ocr_debug"


# ============================================================
# OCR Engine Check
# ============================================================


def is_tesseract_available() -> bool:
    """
    PC에 Tesseract OCR 실행 파일이 설치되어 있는지 확인한다.
    pytesseract 라이브러리만 설치되어 있고,
    실제 Tesseract 프로그램이 없으면 OCR이 동작하지 않는다.
    """
    return shutil.which("tesseract") is not None


def import_pytesseract():
    """
    pytesseract를 안전하게 import한다.
    설치되어 있지 않으면 None을 반환한다.
    """
    try:
        import pytesseract

        return pytesseract
    except ImportError:
        return None


# ============================================================
# Unicode-safe OpenCV Image IO
# ============================================================


def read_image(image_path: Path):
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

    data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

    return image


def save_image(image_path: Path, image):
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
    return PROJECT_ROOT / relative_path


def to_project_relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def ensure_same_size(reference_img, capture_img):
    ref_h, ref_w = reference_img.shape[:2]
    cap_h, cap_w = capture_img.shape[:2]

    if (ref_h, ref_w) == (cap_h, cap_w):
        return capture_img, False

    resized_capture = cv2.resize(
        capture_img, (ref_w, ref_h), interpolation=cv2.INTER_AREA
    )
    return resized_capture, True


def crop_bbox(image, bbox, padding: int = 8):
    x, y, w, h = bbox

    img_h, img_w = image.shape[:2]

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)

    crop = image[y1:y2, x1:x2]

    return crop, [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]


def normalize_lcd_symbols(text: str) -> str:
    """
    의미는 같지만 표현 형식만 다른 LCD/OCR 문자를 통일한다.

    실제 의미를 바꿀 수 있는 O/0, I/1, l/1은 변환하지 않는다.
    """
    if text is None:
        return ""

    normalized = unicodedata.normalize(
        "NFKC",
        str(text),
    )

    normalized = normalized.replace("ºC", "°C")

    normalized = re.sub(
        r"°\s*C",
        "°C",
        normalized,
        flags=re.IGNORECASE,
    )

    return normalized


def normalize_text(text: str) -> str:
    """
    OCR 결과 비교를 위한 기본 정규화.
    너무 강하게 정규화하지 않고, 줄바꿈/양끝 공백 정도만 정리한다.
    """
    if text is None:
        return ""

    text = normalize_lcd_symbols(text)
    text = text.replace("\r", "\n")
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    return text


def compact_text(text: str) -> str:
    """
    비교 보조용.
    공백과 줄바꿈을 모두 제거해서 내용이 같은지 느슨하게 비교한다.
    """
    text = normalize_text(text)
    text = re.sub(r"\s+", "", text)
    return text


def extract_numbers(text: str):
    normalized = normalize_lcd_symbols(text)

    return re.findall(
        r"\d+(?:\.\d+)?",
        normalized,
    )


def compare_ocr_text(reference_text: str, capture_text: str):
    """
    reference OCR 결과와 capture OCR 결과를 비교한다.

    exact_match:
    - 줄바꿈과 공백 정리 후 완전 일치

    compact_match:
    - 공백 제거 후 일치
    - 위치/줄바꿈 차이는 있지만 내용이 비슷한 경우 참고

    number_match:
    - 숫자 목록이 같은지 확인
    """
    ref_norm = normalize_text(reference_text)
    cap_norm = normalize_text(capture_text)

    ref_compact = compact_text(reference_text)
    cap_compact = compact_text(capture_text)

    ref_numbers = extract_numbers(reference_text)
    cap_numbers = extract_numbers(capture_text)

    exact_match = ref_norm == cap_norm and ref_norm != ""
    compact_match = ref_compact == cap_compact and ref_compact != ""
    number_match = ref_numbers == cap_numbers

    if exact_match:
        status = "PASS"
        reason = "OCR text exact match"
    elif compact_match:
        status = "PASS"
        reason = "OCR text compact match"
    elif ref_compact == "" and cap_compact == "":
        status = "NO_TEXT"
        reason = "No reliable OCR text detected"
    elif number_match and ref_numbers:
        status = "REVIEW"
        reason = "Numbers match but text differs"
    else:
        status = "REVIEW"
        reason = "OCR text differs or recognition is uncertain"

    return {
        "ocr_compare_status": status,
        "ocr_compare_reason": reason,
        "reference_text_normalized": ref_norm,
        "capture_text_normalized": cap_norm,
        "reference_text_compact": ref_compact,
        "capture_text_compact": cap_compact,
        "reference_numbers": ref_numbers,
        "capture_numbers": cap_numbers,
        "exact_match": exact_match,
        "compact_match": compact_match,
        "number_match": number_match,
    }


# ============================================================
# OCR Preprocessing
# ============================================================


def preprocess_for_ocr(crop):
    """
    OCR 성능을 조금 높이기 위한 전처리.
    LCD 화면이 어두운 배경 + 밝은 글자인 경우가 많아서
    grayscale, 확대, threshold를 적용한다.
    """
    if crop.size == 0:
        return crop

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # OCR이 작은 글자에 약하므로 확대
    scale = 2
    gray = cv2.resize(
        gray,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_CUBIC,
    )

    # 대비 강화
    gray = cv2.equalizeHist(gray)

    # 이진화
    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    return binary


def run_ocr_on_crop(pytesseract, crop, lang="eng+chi_tra+jpn"):
    """
    crop 이미지에 OCR 수행.
    중국어/일본어 언어팩이 없으면 오류가 날 수 있으므로
    실패 시 eng로 한 번 더 시도한다.
    """
    if crop.size == 0:
        return {
            "text": "",
            "mean_confidence": 0.0,
            "word_count": 0,
            "ocr_error": "empty crop",
        }

    processed = preprocess_for_ocr(crop)

    config = "--psm 6"

    try:
        data = pytesseract.image_to_data(
            processed,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as e:
        # 언어팩 문제일 가능성이 있으므로 eng로 fallback
        try:
            data = pytesseract.image_to_data(
                processed,
                lang="eng",
                config=config,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as e2:
            return {
                "text": "",
                "mean_confidence": 0.0,
                "word_count": 0,
                "ocr_error": f"{e} / fallback eng error: {e2}",
            }

    words = []
    confidences = []

    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        text = str(text).strip()

        try:
            conf_value = float(conf)
        except ValueError:
            conf_value = -1

        if text and conf_value >= 0:
            words.append(text)
            confidences.append(conf_value)

    full_text = " ".join(words)
    mean_conf = round(float(np.mean(confidences)) / 100, 4) if confidences else 0.0

    return {
        "text": full_text,
        "mean_confidence": mean_conf,
        "word_count": len(words),
        "ocr_error": "",
    }


def make_ocr_debug_image(
    reference_crop, capture_crop, reference_text, capture_text, roi_id, status
):
    """
    OCR 확인용 debug 이미지.
    왼쪽 reference crop, 오른쪽 capture crop을 붙이고 OCR 결과를 상단에 표시한다.
    """
    capture_crop, _ = ensure_same_size(reference_crop, capture_crop)

    ref_vis = reference_crop.copy()
    cap_vis = capture_crop.copy()

    h, w = ref_vis.shape[:2]
    header_h = 70

    def add_header(img, title, text):
        canvas = np.full((h + header_h, w, 3), 255, dtype=np.uint8)
        canvas[header_h:, :] = img

        cv2.putText(
            canvas,
            title,
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

        short_text = text[:30] if text else ""
        cv2.putText(
            canvas,
            short_text,
            (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )

        return canvas

    ref_panel = add_header(ref_vis, "REFERENCE OCR", reference_text)
    cap_panel = add_header(cap_vis, "CAPTURE OCR", capture_text)

    combined = cv2.hconcat([ref_panel, cap_panel])

    final_header_h = 45
    total_h, total_w = combined.shape[:2]

    final_canvas = np.full((total_h + final_header_h, total_w, 3), 255, dtype=np.uint8)
    final_canvas[final_header_h:, :] = combined

    title = f"{roi_id} | OCR={status}"

    cv2.putText(
        final_canvas,
        title,
        (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )

    return final_canvas


# ============================================================
# Load Detected ROIs
# ============================================================


def load_detected_rois():
    if not DETECTED_ROIS_PATH.exists():
        raise FileNotFoundError(
            f"{DETECTED_ROIS_PATH} 파일이 없습니다. "
            "먼저 python modules/diff_detector.py를 실행하세요."
        )

    with open(DETECTED_ROIS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Main OCR Logic
# ============================================================


def process_one_item(file_name, item, pytesseract, ocr_available: bool):
    screen_id = item["screen_id"]
    category = item["category"]
    profile = item["profile"]

    reference_path = to_abs_path(item["reference_image"])
    capture_path = to_abs_path(item["capture_image"])

    reference_img = read_image(reference_path)
    capture_img = read_image(capture_path)
    capture_img, full_resized = ensure_same_size(reference_img, capture_img)

    roi_results = []

    for roi in item.get("rois", []):
        roi_id = roi["roi_id"]
        bbox = roi["bbox"]

        ref_crop, padded_bbox = crop_bbox(reference_img, bbox, padding=8)
        cap_crop, _ = crop_bbox(capture_img, bbox, padding=8)

        if not ocr_available:
            reference_ocr = {
                "text": "",
                "mean_confidence": 0.0,
                "word_count": 0,
                "ocr_error": "Tesseract OCR is not available",
            }
            capture_ocr = {
                "text": "",
                "mean_confidence": 0.0,
                "word_count": 0,
                "ocr_error": "Tesseract OCR is not available",
            }
            compare_result = {
                "ocr_compare_status": "SKIPPED",
                "ocr_compare_reason": "Tesseract OCR is not available",
                "reference_text_normalized": "",
                "capture_text_normalized": "",
                "reference_text_compact": "",
                "capture_text_compact": "",
                "reference_numbers": [],
                "capture_numbers": [],
                "exact_match": False,
                "compact_match": False,
                "number_match": False,
            }
        else:
            reference_ocr = run_ocr_on_crop(pytesseract, ref_crop)
            capture_ocr = run_ocr_on_crop(pytesseract, cap_crop)

            compare_result = compare_ocr_text(
                reference_text=reference_ocr["text"],
                capture_text=capture_ocr["text"],
            )

        debug_path = OCR_DEBUG_DIR / screen_id / f"{roi_id}_ocr.jpg"

        if ref_crop.size > 0 and cap_crop.size > 0:
            debug_image = make_ocr_debug_image(
                reference_crop=ref_crop,
                capture_crop=cap_crop,
                reference_text=reference_ocr["text"],
                capture_text=capture_ocr["text"],
                roi_id=roi_id,
                status=compare_result["ocr_compare_status"],
            )
            save_image(debug_path, debug_image)

        roi_result = {
            "roi_id": roi_id,
            "bbox": bbox,
            "padded_bbox": padded_bbox,
            "diff_pixel_area": roi.get("diff_pixel_area"),
            "area_ratio": roi.get("area_ratio"),
            "reference_ocr": reference_ocr,
            "capture_ocr": capture_ocr,
            "ocr_compare": compare_result,
            "debug_image": to_project_relative_path(debug_path),
        }

        roi_results.append(roi_result)

    pass_count = sum(
        1 for r in roi_results if r["ocr_compare"]["ocr_compare_status"] == "PASS"
    )
    review_count = sum(
        1 for r in roi_results if r["ocr_compare"]["ocr_compare_status"] == "REVIEW"
    )
    no_text_count = sum(
        1 for r in roi_results if r["ocr_compare"]["ocr_compare_status"] == "NO_TEXT"
    )
    skipped_count = sum(
        1 for r in roi_results if r["ocr_compare"]["ocr_compare_status"] == "SKIPPED"
    )

    return {
        "screen_id": screen_id,
        "file_name": file_name,
        "category": category,
        "profile": profile,
        "reference_image": item["reference_image"],
        "capture_image": item["capture_image"],
        "diff_roi_count": item.get("diff_roi_count", 0),
        "total_diff_area_ratio": item.get("total_diff_area_ratio"),
        "full_capture_resized_to_reference": full_resized,
        "ocr_summary": {
            "pass_count": pass_count,
            "review_count": review_count,
            "no_text_count": no_text_count,
            "skipped_count": skipped_count,
        },
        "roi_results": roi_results,
    }


def run_ocr_check():
    detected_rois = load_detected_rois()
    items = detected_rois.get("results", {})

    pytesseract = import_pytesseract()
    ocr_available = pytesseract is not None and is_tesseract_available()

    results = {}
    errors = []

    print("========== OCR ENGINE CHECK ==========")
    print(f"pytesseract installed : {pytesseract is not None}")
    print(f"tesseract available   : {is_tesseract_available()}")
    print(f"OCR available         : {ocr_available}")
    print("======================================")

    for idx, (file_name, item) in enumerate(sorted(items.items()), start=1):
        print(f"[{idx:03d}/{len(items)}] OCR checking {file_name}")

        try:
            result = process_one_item(
                file_name=file_name,
                item=item,
                pytesseract=pytesseract,
                ocr_available=ocr_available,
            )
            results[file_name] = result

        except Exception as e:
            errors.append(
                {
                    "file_name": file_name,
                    "error": str(e),
                }
            )
            print(f"  ERROR: {e}")

    summary = {
        "total_items": len(items),
        "processed_count": len(results),
        "error_count": len(errors),
        "ocr_available": ocr_available,
        "items_with_ocr_pass": sum(
            1 for item in results.values() if item["ocr_summary"]["pass_count"] > 0
        ),
        "items_with_ocr_review": sum(
            1 for item in results.values() if item["ocr_summary"]["review_count"] > 0
        ),
        "items_with_no_text": sum(
            1 for item in results.values() if item["ocr_summary"]["no_text_count"] > 0
        ),
        "items_with_ocr_skipped": sum(
            1 for item in results.values() if item["ocr_summary"]["skipped_count"] > 0
        ),
        "errors": errors,
    }

    output = {
        "summary": summary,
        "results": results,
    }

    OCR_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OCR_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


def print_summary(output):
    summary = output["summary"]

    print("\n========== OCR CHECKER SUMMARY ==========")
    print(f"Total items            : {summary['total_items']}")
    print(f"Processed count        : {summary['processed_count']}")
    print(f"Error count            : {summary['error_count']}")
    print(f"OCR available          : {summary['ocr_available']}")
    print(f"Items with OCR PASS    : {summary['items_with_ocr_pass']}")
    print(f"Items with OCR REVIEW  : {summary['items_with_ocr_review']}")
    print(f"Items with NO TEXT     : {summary['items_with_no_text']}")
    print(f"Items with OCR SKIPPED : {summary['items_with_ocr_skipped']}")
    print("-----------------------------------------")
    print(f"Saved JSON             : {OCR_RESULTS_PATH}")
    print(f"Debug images           : {OCR_DEBUG_DIR}")
    print("=========================================")


def main():
    output = run_ocr_check()
    print_summary(output)


if __name__ == "__main__":
    main()
