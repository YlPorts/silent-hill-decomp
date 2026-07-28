#!/usr/bin/env python3
"""Configure one reproducible Android ABI/version variant for GitHub Actions."""

from argparse import ArgumentParser
from pathlib import Path
import re

ANDROID_ROOT = Path(__file__).resolve().parents[1]
GRADLE = ANDROID_ROOT / "app" / "build.gradle"


def replace_one(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return updated


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--abi", required=True, choices=("arm64-v8a", "armeabi-v7a"))
    parser.add_argument("--version-code", required=True, type=int)
    parser.add_argument("--version-name", required=True)
    args = parser.parse_args()

    text = GRADLE.read_text(encoding="utf-8")
    text = replace_one(text, r'^\s*versionCode\s+\d+\s*$',
                       f'        versionCode {args.version_code}', "versionCode")
    text = replace_one(text, r'^\s*versionName\s+"[^"]+"\s*$',
                       f'        versionName "{args.version_name}"', "versionName")
    text = replace_one(text, r'^\s*abiFilters\s+"[^"]+"\s*$',
                       f'            abiFilters "{args.abi}"', "abiFilters")
    GRADLE.write_text(text, encoding="utf-8")
    print(f"Configured Android variant: ABI={args.abi}, version={args.version_name}")


if __name__ == "__main__":
    main()
