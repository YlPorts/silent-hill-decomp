#!/usr/bin/env python3
"""Execute patch_android_runtime_guard.py with corrected idempotency semantics.

The original helper treated the mere presence of a marker as proof that a regex
replacement had completed. Two replacements deliberately share markers with an
earlier step, so they could be skipped prematurely. This wrapper changes the
check to skip only when the old pattern is no longer present, then executes the
same reviewed patch body.
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
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
'''
if source.count(old_helper) != 1:
    raise RuntimeError("runtime guard helper layout changed; refusing an unverified execution")
source = source.replace(old_helper, new_helper, 1)
exec(compile(source, str(SCRIPT), "exec"), {"__name__": "__main__", "__file__": str(SCRIPT)})
