import csv
import copy
import json
import unittest

from modules.decision_engine import (
    OCR_RESULTS_PATH,
    SSIM_RESULTS_PATH,
    decide_one_item,
    expected_to_binary,
    has_bidirectional_text_presence_difference,
    has_spacing_mismatch,
)
from modules.path_config import (
    DETECTED_ROIS_PATH,
    INSPECTION_PROFILES_PATH,
    INSPECTION_RESULTS_PATH,
    REFERENCE_REGISTRY_PATH,
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class BinaryDecisionEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.diff_items = load_json(DETECTED_ROIS_PATH)["results"]
        cls.ssim_items = load_json(SSIM_RESULTS_PATH)["results"]
        cls.ocr_items = load_json(OCR_RESULTS_PATH)["results"]
        cls.binary_policy = load_json(INSPECTION_PROFILES_PATH)["binary_policy"]
        cls.output = load_json(INSPECTION_RESULTS_PATH)

        with open(
            REFERENCE_REGISTRY_PATH,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            cls.registry = {
                row["file_name"]: row for row in csv.DictReader(f) if row["file_name"]
            }

    def test_final_output_contains_only_pass_or_fail(self):
        statuses = {
            item["final_status"] for item in self.output.get("results", {}).values()
        }
        self.assertLessEqual(statuses, {"PASS", "FAIL"})
        self.assertNotIn("REVIEW", statuses)

    def test_expected_result_is_not_used_for_decision(self):
        for file_name, diff_item in self.diff_items.items():
            base_row = dict(self.registry[file_name])
            pass_row = dict(base_row, expected_result="PASS")
            fail_row = dict(base_row, expected_result="FAIL")

            pass_label_result = decide_one_item(
                file_name,
                diff_item,
                self.ssim_items.get(file_name, {}),
                self.ocr_items.get(file_name, {}),
                pass_row,
                self.binary_policy,
            )
            fail_label_result = decide_one_item(
                file_name,
                diff_item,
                self.ssim_items.get(file_name, {}),
                self.ocr_items.get(file_name, {}),
                fail_row,
                self.binary_policy,
            )

            self.assertEqual(
                pass_label_result["final_status"],
                fail_label_result["final_status"],
                msg=f"expected_result가 판정에 영향을 줌: {file_name}",
            )

    def test_original_review_maps_to_binary_fail_for_evaluation(self):
        self.assertEqual(expected_to_binary("PASS", self.binary_policy), "PASS")
        self.assertEqual(expected_to_binary("REVIEW", self.binary_policy), "FAIL")
        self.assertEqual(expected_to_binary("FAIL", self.binary_policy), "FAIL")

    def test_progress_bar_is_measured_not_hard_coded_by_file_name(self):
        review_case = self.output["results"]["13-12.png"]
        allowed_case = self.output["results"]["13-2.png"]
        threshold = self.binary_policy["status_time"][
            "progress_bar_fill_delta_fail"
        ]

        self.assertGreaterEqual(
            review_case["evidence_summary"]["progress_bar"]["fill_delta"],
            threshold,
        )
        self.assertLess(
            allowed_case["evidence_summary"]["progress_bar"]["fill_delta"],
            threshold,
        )

    def test_dynamic_card_background_is_ignored(self):
        item = self.output["results"]["3-23.png"]
        self.assertEqual(item["final_status"], "PASS")
        self.assertEqual(item["applied_rule"], "within_tolerance")

    def test_gradient_color_failures_use_visual_evidence(self):
        expected_rules = {
            "14-24.png": "card_ui_gradient_color_difference",
            "14-25.png": "card_ui_gradient_color_difference",
            "18-3.png": "popup_gradient_color_difference",
            "18-4.png": "popup_gradient_color_difference",
            "18-5.png": "popup_gradient_color_difference",
        }

        for file_name, rule_name in expected_rules.items():
            with self.subTest(file_name=file_name):
                item = self.output["results"][file_name]
                self.assertEqual(item["final_status"], "FAIL")
                self.assertEqual(item["applied_rule"], rule_name)

    def test_faded_setting_text_uses_brightness_not_font_shape(self):
        item = self.output["results"]["4-1.png"]
        self.assertEqual(item["final_status"], "FAIL")
        self.assertEqual(item["applied_rule"], "setting_text_brightness_loss")
        self.assertGreaterEqual(
            item["evidence_summary"]["localized_text_brightness"][
                "max_brightness_loss"
            ],
            self.binary_policy["setting_control"][
                "localized_brightness_loss_fail"
            ],
        )

    def test_progress_bar_check_can_be_disabled(self):
        file_name = "13-12.png"
        policy = copy.deepcopy(self.binary_policy)
        policy["enabled_checks"]["progress_bar"] = False
        result = decide_one_item(
            file_name,
            self.diff_items[file_name],
            self.ssim_items.get(file_name, {}),
            self.ocr_items.get(file_name, {}),
            self.registry[file_name],
            policy,
        )
        self.assertEqual(result["final_status"], "PASS")

    def test_korean_semantic_spacing_difference_is_detected(self):
        synthetic_ocr_roi = {
            "reference_ocr": {
                "text": "아버지 가방에 들어가신다",
                "mean_confidence": 0.99,
            },
            "capture_ocr": {
                "text": "아버지가 방에 들어가신다",
                "mean_confidence": 0.99,
            },
        }
        self.assertTrue(has_spacing_mismatch(synthetic_ocr_roi))

    def test_text_presence_difference_is_bidirectional(self):
        rules = self.binary_policy["bidirectional_text_presence"]
        ssim_roi = {"ssim_status": "FAIL"}

        capture_only = {
            "area_ratio": 0.003,
            "reference_ocr": {"mean_confidence": 0.0},
            "capture_ocr": {"mean_confidence": 0.9},
            "ocr_compare": {
                "reference_text_compact": "",
                "capture_text_compact": "確認鍵",
            },
        }
        reference_only = {
            "area_ratio": 0.003,
            "reference_ocr": {"mean_confidence": 0.9},
            "capture_ocr": {"mean_confidence": 0.0},
            "ocr_compare": {
                "reference_text_compact": "確認鍵",
                "capture_text_compact": "",
            },
        }

        self.assertTrue(
            has_bidirectional_text_presence_difference(
                capture_only,
                ssim_roi,
                rules,
            )
        )
        self.assertTrue(
            has_bidirectional_text_presence_difference(
                reference_only,
                ssim_roi,
                rules,
            )
        )


if __name__ == "__main__":
    unittest.main()
