#!/usr/bin/env python3
"""Fix Android GLES VRAM, mobile memory use, and first ordering-table draw.

Android uses an OpenGL ES 3 context. PsyCross still selected the legacy
GL_LUMINANCE_ALPHA VRAM texture and the PC GS stub called desktop glClearDepth.
The mobile build also reserved desktop-sized PGXP shadow tables before the title
screen. Apply checked Android-only replacements while leaving desktop builds
unchanged.
"""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"
RENDER_HEADER = PSYCROSS / "include" / "PsyX" / "PsyX_render.h"
GPU = PSYCROSS / "src" / "gpu" / "PsyX_GPU.cpp"
LIBGPU = PSYCROSS / "src" / "psx" / "libgpu.c"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"[already applied] {label}")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected source fragment exactly once in {path}, found {count}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[applied] {label}")


def patch_libgs() -> None:
    replace_once(
        LIBGS,
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

    replace_once(
        LIBGS,
        """        glClearDepth(1.0f);
        glClear(GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT);
#endif
        DrawOTag((u_long*)ot->tag);
""",
        """#ifdef __ANDROID__
        /* GLES exposes glClearDepthf, not desktop glClearDepth. */
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
        "use GLES depth clear before the ordering table",
    )

    replace_once(
        LIBGS,
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


def patch_vram_format_and_mobile_buffers() -> None:
    replace_once(
        RENDER_HEADER,
        """#if defined(RENDERER_OGL)
#\tdefine VRAM_FORMAT            GL_RG
#\tdefine VRAM_INTERNAL_FORMAT   GL_RG8
#elif defined(RENDERER_OGLES)
#\tdefine VRAM_FORMAT            GL_LUMINANCE_ALPHA
#\tdefine VRAM_INTERNAL_FORMAT   GL_LUMINANCE_ALPHA
#endif
""",
        """#if defined(RENDERER_OGL)
#\tdefine VRAM_FORMAT            GL_RG
#\tdefine VRAM_INTERNAL_FORMAT   GL_RG8
#elif defined(RENDERER_OGLES) && (OGLES_VERSION >= 3)
/* GLES3 removed the legacy LUMINANCE_ALPHA texture format. Keep each PSX
 * RGB555 word as two exact normalized bytes in RG8, matching the shader's
 * low-byte/high-byte reconstruction and avoiding the red/corrupt palette. */
#\tdefine VRAM_FORMAT            GL_RG
#\tdefine VRAM_INTERNAL_FORMAT   GL_RG8
#elif defined(RENDERER_OGLES)
#\tdefine VRAM_FORMAT            GL_LUMINANCE_ALPHA
#\tdefine VRAM_INTERNAL_FORMAT   GL_LUMINANCE_ALPHA
#endif
""",
        "use RG8 VRAM storage on OpenGL ES 3",
    )

    replace_once(
        RENDER_HEADER,
        "#define MAX_VERTEX_BUFFER_SIZE\t(1 << 18)\n",
        """#if defined(__ANDROID__)
/* Mobile scenes stream/flush this buffer. Half the desktop whole-town size
 * saves both a large native array and two equally large GLES VBO allocations. */
#define MAX_VERTEX_BUFFER_SIZE\t(1 << 17)
#else
#define MAX_VERTEX_BUFFER_SIZE\t(1 << 18)
#endif
""",
        "reduce the Android streaming vertex buffer",
    )

    replace_once(
        GPU,
        "#define SHADOW_BITS 21\n",
        """#if defined(__ANDROID__)
/* PGXP/per-pixel flashlight are disabled in the safe mobile profile. Do not
 * reserve desktop-sized shadow hash tables before the title screen. */
#define SHADOW_BITS 17
#else
#define SHADOW_BITS 21
#endif
""",
        "reduce Android-only PGXP shadow tables",
    )


def patch_shared_draw_trace() -> None:
    replace_once(
        LIBGPU,
        """#include "PsyX/PsyX_globals.h"
#include "../PsyX_main.h"
#include "../gpu/font.h"

int g_dbg_emulatorPaused = 0;
""",
        """#include "PsyX/PsyX_globals.h"
#include "../PsyX_main.h"
#include "../gpu/font.h"

#ifdef __ANDROID__
extern void PcPort_WriteStartupStatus(const char* status);
static int s_androidFirstOtTrace = 1;
#define ANDROID_OT_STAGE(stage) do { if (s_androidFirstOtTrace) PcPort_WriteStartupStatus(stage); } while (0)
#else
#define ANDROID_OT_STAGE(stage) ((void)0)
#endif

int g_dbg_emulatorPaused = 0;
""",
        "add first ordering-table trace helper",
    )

    replace_once(
        LIBGPU,
        """\t\tif (PsyX_BeginScene())
\t\t{
\t\t\tClearSplits();
\t\t}

\t\t//if (activeDrawEnv.isbg)
\t\t//\tClearImage(&activeDrawEnv.clip, activeDrawEnv.r0, activeDrawEnv.g0, activeDrawEnv.b0);

\t\tParsePrimitivesLinkedList(p, 0);

\t\t/* No glFinish here: the parse is CPU-side and the GL command stream is
""",
        """\t\tANDROID_OT_STAGE("FIRST_FRAME_BEGIN_SCENE");
\t\tif (PsyX_BeginScene())
\t\t{
\t\t\tClearSplits();
\t\t}
\t\tANDROID_OT_STAGE("FIRST_FRAME_BEGIN_SCENE_READY");

\t\t//if (activeDrawEnv.isbg)
\t\t//\tClearImage(&activeDrawEnv.clip, activeDrawEnv.r0, activeDrawEnv.g0, activeDrawEnv.b0);

\t\tANDROID_OT_STAGE("FIRST_FRAME_OT_WALK");
\t\tParsePrimitivesLinkedList(p, 0);
\t\tANDROID_OT_STAGE("FIRST_FRAME_OT_WALK_READY");

\t\t/* No glFinish here: the parse is CPU-side and the GL command stream is
""",
        "trace begin-scene and primitive walk",
    )

    replace_once(
        LIBGPU,
        """\t\tDrawAllSplits();
\t} while (g_dbg_emulatorPaused);
}
""",
        """\t\tANDROID_OT_STAGE("FIRST_FRAME_DRAW_SPLITS");
\t\tDrawAllSplits();
\t\tANDROID_OT_STAGE("FIRST_FRAME_DRAW_SPLITS_READY");
#ifdef __ANDROID__
\t\ts_androidFirstOtTrace = 0;
#endif
\t} while (g_dbg_emulatorPaused);
}
""",
        "trace vertex upload and split drawing",
    )


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_libgs()
    patch_vram_format_and_mobile_buffers()
    patch_shared_draw_trace()
    print("Android GLES VRAM and ordering-table fixes applied successfully.")
