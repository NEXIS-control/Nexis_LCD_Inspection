"""여러 발표용 이미지 세트를 한 프로젝트 안에서 안전하게 관리한다."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from modules.path_config import (
        BASE_DATA_DIR,
        BASE_RESULTS_DIR,
        DEFAULT_SCENARIO_ID,
        IMAGE_EXTENSIONS,
        PROJECT_ROOT,
        SCENARIO_DATA_ROOT,
        SCENARIO_ENV_VAR,
        SCENARIO_RESULTS_ROOT,
        validate_scenario_id,
    )
except ModuleNotFoundError:
    from path_config import (
        BASE_DATA_DIR,
        BASE_RESULTS_DIR,
        DEFAULT_SCENARIO_ID,
        IMAGE_EXTENSIONS,
        PROJECT_ROOT,
        SCENARIO_DATA_ROOT,
        SCENARIO_ENV_VAR,
        SCENARIO_RESULTS_ROOT,
        validate_scenario_id,
    )


METADATA_FILE_NAME = "scenario.json"


def scenario_data_dir(scenario_id: str) -> Path:
    checked_id = validate_scenario_id(scenario_id)
    if checked_id == DEFAULT_SCENARIO_ID:
        return BASE_DATA_DIR
    return SCENARIO_DATA_ROOT / checked_id


def scenario_results_dir(scenario_id: str) -> Path:
    checked_id = validate_scenario_id(scenario_id)
    if checked_id == DEFAULT_SCENARIO_ID:
        return BASE_RESULTS_DIR
    return SCENARIO_RESULTS_ROOT / checked_id


def reference_dir(scenario_id: str) -> Path:
    return scenario_data_dir(scenario_id) / "reference"


def capture_dir(scenario_id: str) -> Path:
    return scenario_data_dir(scenario_id) / "capture"


def metadata_path(scenario_id: str) -> Path:
    return scenario_data_dir(scenario_id) / METADATA_FILE_NAME


def image_names(directory: Path):
    if not directory.exists():
        return set()
    return {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    }


def load_metadata(scenario_id: str):
    path = metadata_path(scenario_id)
    if not path.exists():
        return {
            "scenario_id": validate_scenario_id(scenario_id),
            "label": (
                "기본 데이터" if scenario_id == DEFAULT_SCENARIO_ID else scenario_id
            ),
        }

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_metadata(scenario_id: str, label: str, source_scenario: str = ""):
    path = metadata_path(scenario_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "scenario_id": validate_scenario_id(scenario_id),
        "label": label.strip() or scenario_id,
        "source_scenario": source_scenario,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)


def create_scenario(scenario_id: str, label: str):
    checked_id = validate_scenario_id(scenario_id)
    if checked_id == DEFAULT_SCENARIO_ID:
        raise ValueError("default는 기존 data/reference와 data/capture를 뜻합니다.")

    data_dir = scenario_data_dir(checked_id)
    existed = data_dir.exists()
    reference_dir(checked_id).mkdir(parents=True, exist_ok=True)
    capture_dir(checked_id).mkdir(parents=True, exist_ok=True)
    scenario_results_dir(checked_id).mkdir(parents=True, exist_ok=True)

    if not metadata_path(checked_id).exists():
        save_metadata(checked_id, label)

    print(f"Scenario ID : {checked_id}")
    print(f"Label       : {load_metadata(checked_id).get('label', checked_id)}")
    print(f"Data folder : {data_dir}")
    print(f"Result folder: {scenario_results_dir(checked_id)}")
    print("기존 폴더를 유지했습니다." if existed else "새 시나리오를 만들었습니다.")


def copy_images(source_dir: Path, destination_dir: Path):
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in sorted(source_dir.iterdir()):
        if source.is_file() and source.suffix.lower() in IMAGE_EXTENSIONS:
            shutil.copy2(source, destination_dir / source.name)
            copied += 1
    return copied


def clone_scenario(source_id: str, target_id: str, label: str):
    checked_source = validate_scenario_id(source_id)
    checked_target = validate_scenario_id(target_id)

    if checked_target == DEFAULT_SCENARIO_ID:
        raise ValueError("default 폴더를 복제 대상 이름으로 사용할 수 없습니다.")
    target_has_data = bool(
        image_names(reference_dir(checked_target))
        or image_names(capture_dir(checked_target))
        or metadata_path(checked_target).exists()
    )
    if target_has_data:
        raise FileExistsError(
            f"대상 시나리오가 이미 있습니다: {scenario_data_dir(checked_target)}"
        )
    if (
        not reference_dir(checked_source).exists()
        or not capture_dir(checked_source).exists()
    ):
        raise FileNotFoundError("복제할 시나리오의 reference/capture가 없습니다.")

    reference_count = copy_images(
        reference_dir(checked_source),
        reference_dir(checked_target),
    )
    capture_count = copy_images(
        capture_dir(checked_source),
        capture_dir(checked_target),
    )
    scenario_results_dir(checked_target).mkdir(parents=True, exist_ok=True)
    save_metadata(checked_target, label, checked_source)

    print(f"{checked_source} -> {checked_target} 복제 완료")
    print(f"Reference copied: {reference_count}")
    print(f"Capture copied  : {capture_count}")
    print("결과 파일은 복제하지 않았습니다. run 명령으로 새로 판정하세요.")


def add_pair(
    scenario_id: str,
    reference_source: str,
    capture_source: str,
    file_name: str = "",
    overwrite: bool = False,
):
    checked_id = validate_scenario_id(scenario_id)
    if checked_id == DEFAULT_SCENARIO_ID:
        raise ValueError("안전을 위해 add-pair는 default에 사용할 수 없습니다.")

    reference_source_path = Path(reference_source).resolve()
    capture_source_path = Path(capture_source).resolve()

    for source in (reference_source_path, capture_source_path):
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"이미지 파일이 없습니다: {source}")
        if source.suffix.lower() not in IMAGE_EXTENSIONS:
            raise ValueError(f"지원하지 않는 이미지 확장자입니다: {source.suffix}")

    target_name = file_name.strip() or reference_source_path.name
    if Path(target_name).name != target_name:
        raise ValueError("--file-name에는 폴더 없이 파일명만 입력하세요.")
    if Path(target_name).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError("--file-name에 이미지 확장자를 포함하세요. 예: 4-9.png")

    target_reference = reference_dir(checked_id) / target_name
    target_capture = capture_dir(checked_id) / target_name
    existing = [path for path in (target_reference, target_capture) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "대상 파일이 이미 있습니다. 교체하려면 --overwrite를 추가하세요: "
            + ", ".join(str(path) for path in existing)
        )

    target_reference.parent.mkdir(parents=True, exist_ok=True)
    target_capture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(reference_source_path, target_reference)
    shutil.copy2(capture_source_path, target_capture)

    print(f"Pair added: {checked_id}/{target_name}")
    print(f"Reference: {target_reference}")
    print(f"Capture  : {target_capture}")


def collect_scenario_ids():
    scenario_ids = [DEFAULT_SCENARIO_ID]
    if SCENARIO_DATA_ROOT.exists():
        scenario_ids.extend(
            path.name for path in sorted(SCENARIO_DATA_ROOT.iterdir()) if path.is_dir()
        )
    return scenario_ids


def print_scenarios():
    print("================ SCENARIOS ================")
    for scenario_id in collect_scenario_ids():
        reference_names = image_names(reference_dir(scenario_id))
        capture_names = image_names(capture_dir(scenario_id))
        metadata = load_metadata(scenario_id)
        result_exists = (
            scenario_results_dir(scenario_id) / "inspection_results.json"
        ).exists()
        print(
            f"{scenario_id:22} | {metadata.get('label', scenario_id):16} | "
            f"ref={len(reference_names):3} cap={len(capture_names):3} "
            f"matched={len(reference_names & capture_names):3} "
            f"result={'YES' if result_exists else 'NO'}"
        )
    print("===========================================")


def validate_runnable_scenario(scenario_id: str):
    checked_id = validate_scenario_id(scenario_id)
    reference_names = image_names(reference_dir(checked_id))
    capture_names = image_names(capture_dir(checked_id))
    matched_names = reference_names & capture_names

    if not matched_names:
        raise ValueError(
            "같은 파일명을 가진 reference/capture 쌍이 없습니다. "
            "예: reference/4-9.png와 capture/4-9.png"
        )

    if reference_names != capture_names:
        print("주의: 한쪽에만 있는 파일은 매칭에서 제외됩니다.")
        print(f"Reference only: {sorted(reference_names - capture_names)}")
        print(f"Capture only  : {sorted(capture_names - reference_names)}")

    return checked_id, len(matched_names)


def run_module_for_scenario(scenario_id: str, module_name: str):
    checked_id, matched_count = validate_runnable_scenario(scenario_id)
    environment = os.environ.copy()
    environment[SCENARIO_ENV_VAR] = checked_id

    print(f"Scenario: {checked_id}")
    print(f"Matched pairs: {matched_count}")
    print(f"Running: python -m {module_name}")

    completed = subprocess.run(
        [sys.executable, "-m", module_name],
        cwd=str(PROJECT_ROOT),
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{module_name} 실행 실패(returncode={completed.returncode})"
        )


def print_paths(scenario_id: str):
    checked_id = validate_scenario_id(scenario_id)
    metadata = load_metadata(checked_id)
    print(f"Scenario ID : {checked_id}")
    print(f"Label       : {metadata.get('label', checked_id)}")
    print(f"Reference   : {reference_dir(checked_id)}")
    print(f"Capture     : {capture_dir(checked_id)}")
    print(f"Results     : {scenario_results_dir(checked_id)}")


def build_parser():
    parser = argparse.ArgumentParser(description="NEXIS LCD 시나리오 데이터/결과 관리")
    commands = parser.add_subparsers(dest="command", required=True)

    create_parser = commands.add_parser("create", help="빈 시나리오 생성")
    create_parser.add_argument("scenario_id")
    create_parser.add_argument("--label", default="")

    clone_parser = commands.add_parser("clone", help="사진만 다른 시나리오로 복제")
    clone_parser.add_argument("source_id")
    clone_parser.add_argument("target_id")
    clone_parser.add_argument("--label", default="")

    add_parser = commands.add_parser("add-pair", help="reference/capture 한 쌍 추가")
    add_parser.add_argument("scenario_id")
    add_parser.add_argument("--reference", required=True)
    add_parser.add_argument("--capture", required=True)
    add_parser.add_argument("--file-name", default="")
    add_parser.add_argument("--overwrite", action="store_true")

    commands.add_parser("list", help="전체 시나리오 목록")

    paths_parser = commands.add_parser("paths", help="시나리오 폴더 위치 확인")
    paths_parser.add_argument("scenario_id")

    run_parser = commands.add_parser("run", help="해당 시나리오 전체 판독")
    run_parser.add_argument("scenario_id")

    export_parser = commands.add_parser("export", help="Validation Pack 생성")
    export_parser.add_argument("scenario_id")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "create":
        create_scenario(args.scenario_id, args.label)
    elif args.command == "clone":
        clone_scenario(args.source_id, args.target_id, args.label)
    elif args.command == "add-pair":
        add_pair(
            args.scenario_id,
            args.reference,
            args.capture,
            args.file_name,
            args.overwrite,
        )
    elif args.command == "list":
        print_scenarios()
    elif args.command == "paths":
        print_paths(args.scenario_id)
    elif args.command == "run":
        run_module_for_scenario(args.scenario_id, "modules.inspector")
    elif args.command == "export":
        inspection_result = (
            scenario_results_dir(args.scenario_id) / "inspection_results.json"
        )
        if not inspection_result.exists():
            raise FileNotFoundError(
                f"먼저 run 명령으로 판독하세요: {inspection_result}"
            )
        run_module_for_scenario(args.scenario_id, "modules.validation_exporter")


if __name__ == "__main__":
    main()
