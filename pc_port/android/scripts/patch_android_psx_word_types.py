#!/usr/bin/env python3
"""Keep PlayStation SDK word aliases 32-bit on Android, including ARM64.

PsyCross inherits Psy-Q aliases such as u_long/ulong. On Windows x64, C/C++
`unsigned long` is 32-bit, but Android ARM64 follows LP64 and makes it 64-bit.
Those aliases are used for PSX packets and binary data, which must remain
32-bit regardless of host pointer width. Primitive links already use uintptr_t
when USE_EXTENDED_PRIM_POINTERS is enabled, so pointer-sized data stays intact.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
TYPES = PSYCROSS / "include" / "psx" / "types.h"
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[already applied] {label}")
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    print(f"[applied] {label}")
    return text.replace(old, new, 1)


def patch_types() -> None:
    text = TYPES.read_text(encoding="utf-8")

    text = replace_exact(
        text,
        """#ifndef _ULONG_T
#define _ULONG_T
typedef\tunsigned long\tu_long;
#endif
""",
        """#ifndef _ULONG_T
#define _ULONG_T
#if defined(__ANDROID__)
/* A PSX long is always one 32-bit word. Android ARM64 uses LP64, where host
 * unsigned long is 64-bit, so use the fixed-width representation explicitly. */
typedef uint32_t u_long;
#define PSYX_ANDROID_PSX_ULONG_32 1
#else
typedef\tunsigned long\tu_long;
#endif
#endif
""",
        "make u_long a 32-bit PSX word on Android",
    )

    text = replace_exact(
        text,
        """#ifndef _SYSV_ULONG
#define _SYSV_ULONG
typedef\tunsigned long\tulong;\t\t/* sys V compat */
#endif
""",
        """#ifndef _SYSV_ULONG
#define _SYSV_ULONG
#if defined(__ANDROID__)
typedef uint32_t ulong;\t\t/* PSX/System V compatibility word */
#else
typedef\tunsigned long\tulong;\t\t/* sys V compat */
#endif
#endif
""",
        "make ulong a 32-bit PSX word on Android",
    )

    assertion = """
#if defined(__ANDROID__)
# if defined(__cplusplus)
static_assert(sizeof(u_long) == 4, "Android PSX u_long must be 32-bit");
static_assert(sizeof(ulong) == 4, "Android PSX ulong must be 32-bit");
# else
_Static_assert(sizeof(u_long) == 4, "Android PSX u_long must be 32-bit");
_Static_assert(sizeof(ulong) == 4, "Android PSX ulong must be 32-bit");
# endif
#endif

"""
    if "Android PSX u_long must be 32-bit" not in text:
        marker = "#define\tNBBY\t8\n"
        if marker not in text:
            raise RuntimeError("type-width assertion insertion marker not found")
        text = text.replace(marker, assertion + marker, 1)
        print("[applied] add Android PSX word-width assertions")
    else:
        print("[already applied] add Android PSX word-width assertions")

    TYPES.write_text(text, encoding="utf-8")


def remove_render_loop_file_io() -> None:
    text = LIBGS.read_text(encoding="utf-8")
    removed = 0
    for stage in ("FIRST_FRAME_DEPTH_CLEAR", "FIRST_FRAME_PARSE_OT"):
        pattern = re.compile(
            rf'^\s*PcPort_WriteStartupStatus\("{re.escape(stage)}"\);\s*\n',
            re.MULTILINE,
        )
        text, count = pattern.subn("", text, count=1)
        removed += count
        print(f"[{'applied' if count else 'not present'}] remove per-draw status {stage}")
    LIBGS.write_text(text, encoding="utf-8")
    print(f"Removed {removed} render-loop status writes.")


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_types()
    remove_render_loop_file_io()
    print("Android fixed-width PSX word patch applied successfully.")
