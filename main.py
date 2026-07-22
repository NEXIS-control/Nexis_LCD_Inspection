from pathlib import Path

import cv2
import numpy as np
import pandas as pd


def main() -> None:
    """프로젝트 개발 환경과 폴더 구조를 확인한다."""

    project_root = Path(__file__).resolve().parent

    print("=" * 50)
    print("NEXIS LCD Inspection System")
    print("=" * 50)

    print(f"OpenCV version : {cv2.__version__}")
    print(f"NumPy version  : {np.__version__}")
    print(f"Pandas version : {pd.__version__}")
    print(f"Project folder : {project_root}")

    folders = [
        "data/reference",
        "data/capture",
        "config",
        "modules",
        "results",
        "logs",
        "tests",
    ]

    print("\n[폴더 확인]")

    for folder in folders:
        folder_path = project_root / folder
        status = "정상" if folder_path.exists() else "없음"
        print(f"{folder:<20} : {status}")

    print("\n개발 환경 연결 테스트가 완료되었습니다.")


if __name__ == "__main__":
    main()