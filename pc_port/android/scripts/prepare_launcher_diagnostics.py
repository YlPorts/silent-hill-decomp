#!/usr/bin/env python3
"""Prepare the Android launcher to report crashes from the isolated game process."""

from pathlib import Path

ANDROID_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (
    ANDROID_ROOT
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "slickamogus"
    / "silenthill"
    / "LauncherActivity.java"
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    print(f"[applied] {label}")
    return text.replace(old, new, 1)


text = LAUNCHER.read_text(encoding="utf-8")

# Reaching MainLoop does not prove that a frame was displayed. Keep the launch
# marker until the isolated :game process is known to have survived. If it dies,
# LauncherActivity resumes and reports the last native stage.
text = replace_once(
    text,
    '''        if (launchPending && "RUNNING".equals(startupStage)) {
            launchMarkerFile().delete();
            launchPending = false;
        }

''',
    "",
    "preserve crash marker after entering MainLoop",
)

text = replace_once(
    text,
    '            case "RUNNING": return "motor iniciado";\n',
    '            case "RUNNING": return "entrada al bucle principal; el motor se cerró antes de mostrar una imagen";\n',
    "describe MainLoop startup crash",
)

LAUNCHER.write_text(text, encoding="utf-8")
print("Android launcher crash diagnostics prepared successfully.")
