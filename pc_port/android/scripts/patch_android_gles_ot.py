#!/usr/bin/env python3
"""Fix the shared GS ordering-table path for Android OpenGL ES.

The PC stub calls desktop glClearDepth through GLAD at the start of every
GsDrawOt. Android creates an OpenGL ES context, where the entry point is
 glClearDepthf. Calling an unresolved desktop GLAD pointer crashes on the first
OT0 draw before any frame can be presented.
"""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[already applied] {label}")
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    print(f"[applied] {label}")
    return text.replace(old, new, 1)


text = LIBGS.read_text(encoding="utf-8")

text = replace_once(
    text,
    """#include <SDL.h>
#include <PsyX/common/glad.h>
#include <PsyX/PsyX_render.h> /* GR_SetPsxDisplayBuffers */
""",
    """#include <SDL.h>
#if defined(__ANDROID__)
#include <GLES3/gl3.h>
#else
#include <PsyX/common/glad.h>
#endif
#include <PsyX/PsyX_render.h> /* GR_SetPsxDisplayBuffers */
""",
    "use the native GLES header in the GS stub",
)

text = replace_once(
    text,
    """        glClearDepth(1.0f);
        glClear(GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
#endif
        DrawOTag((u_long*)ot->tag);
""",
    """#ifdef __ANDROID__
        /* GLES exposes glClearDepthf, not desktop glClearDepth. The desktop
         * GLAD entry can be NULL under an EGL/GLES context and was crashing
         * exactly on the first GsDrawOt call. */
        PcPort_WriteStartupStatus("FIRST_FRAME_DEPTH_CLEAR");
        glClearDepthf(1.0f);
#else
        glClearDepth(1.0f);
#endif
        glClear(GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
#ifdef __ANDROID__
        PcPort_WriteStartupStatus("FIRST_FRAME_PARSE_OT");
#endif
#endif
        DrawOTag((u_long*)ot->tag);
""",
    "use GLES depth clear before parsing the ordering table",
)

text = replace_once(
    text,
    """#include "sh_log.h"

/* Screenshot helper - captures back buffer (call before EndScene/swap) */
""",
    """#include "sh_log.h"

#ifdef __ANDROID__
extern void PcPort_WriteStartupStatus(const char* status);
#endif

/* Screenshot helper - captures back buffer (call before EndScene/swap) */
""",
    "expose Android startup status to the GS stub",
)

LIBGS.write_text(text, encoding="utf-8")
print("Android GLES ordering-table fix applied successfully.")
