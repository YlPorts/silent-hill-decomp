#!/usr/bin/env python3
"""Execute patch_android_runtime_guard.py with safe regex replacement semantics.

The original helper treated the mere presence of a marker as proof that a regex
replacement had completed, and passed C/C++ replacement text directly through
Python's regex-template parser. This wrapper skips only when the old pattern is
gone and inserts replacement text through a lambda so C escape sequences remain
literal source code. It also masks both primitive attribute bits when validating
packet sizes, matching PsyCross's own primitive dispatch.
"""

from pathlib import Path

SCRIPT = Path(__file__).with_name("patch_android_runtime_guard.py")
source = SCRIPT.read_text(encoding="utf-8")
old_helper = '''    if marker in text:
        print(f"[already applied] {label}")
        return
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
'''
new_helper = '''    old_pattern_still_present = re.search(pattern, text, flags=re.DOTALL) is not None
    if marker in text and not old_pattern_still_present:
        print(f"[already applied] {label}")
        return
    updated, count = re.subn(
        pattern, lambda _match: replacement, text, count=1, flags=re.DOTALL
    )
'''
if source.count(old_helper) != 1:
    raise RuntimeError("runtime guard helper layout changed; refusing an unverified execution")
source = source.replace(old_helper, new_helper, 1)
if source.count("switch (code & 0xFD)") != 1:
    raise RuntimeError("primitive validation mask layout changed")
source = source.replace("switch (code & 0xFD)", "switch (code & 0xFC)", 1)
exec(compile(source, str(SCRIPT), "exec"), {"__name__": "__main__", "__file__": str(SCRIPT)})
