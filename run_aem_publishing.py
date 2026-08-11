#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

PIPELINE = Path("/Users/joshuachung/Documents/projects/aem-publishing/translation_pipeline")
sys.path.insert(0, str(PIPELINE))

import main as publishing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", required=True)
    args, rest = parser.parse_known_args()

    publishing.FILE_PATH = args.workbook
    sys.argv = ["main.py", *rest]
    publishing.main()


if __name__ == "__main__":
    main()
