#!/usr/bin/env python3
"""Extend the generated launcher safe profile for existing installations."""

from pathlib import Path

ANDROID_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (
    ANDROID_ROOT / "app" / "src" / "main" / "java" / "com" /
    "slickamogus" / "silenthill" / "LauncherActivity.java"
)

text = LAUNCHER.read_text(encoding="utf-8")
marker = '{"widescreen_mode", "2"}'
if marker not in text:
    old = '''                    {"msaa", "0"},
                    {"msaa_samples", "0"}
'''
    new = '''                    {"msaa", "0"},
                    {"msaa_samples", "0"},
                    {"widescreen_mode", "2"},
                    {"menu_pillarbox", "0"},
                    {"audio_output", "1"}
'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"launcher safe-value tail: expected one match, found {count}"
        )
    text = text.replace(old, new, 1)
    LAUNCHER.write_text(text, encoding="utf-8")
    print("[applied] force stretched 4:3 presentation and stereo audio")
else:
    print("[already applied] force stretched 4:3 presentation and stereo audio")

for required in (
    '{"widescreen_mode", "2"}',
    '{"menu_pillarbox", "0"}',
    '{"audio_output", "1"}',
):
    if required not in text:
        raise RuntimeError(f"generated launcher is missing {required}")

print("Android launcher runtime defaults verified.")
