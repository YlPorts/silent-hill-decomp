#!/usr/bin/env python3
"""Fix Android GLES VRAM upload, mobile memory use, and ordering-table startup.

Android uses an OpenGL ES 3 context. Some mobile drivers did not preserve the
second byte of the PSX RGB555 word reliably through the two-channel VRAM path,
which left mostly the low byte visible and produced a red/green corrupted image.
Use a universally supported RGBA8 texture on Android and explicitly expand each
16-bit PSX word to R=low byte, G=high byte before uploading. Desktop builds keep
their original renderer path.
"""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"
RENDER_HEADER = PSYCROSS / "include" / "PsyX" / "PsyX_render.h"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"
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
#elif defined(__ANDROID__) && defined(RENDERER_OGLES) && (OGLES_VERSION >= 3)
/* Use RGBA8 as the transport texture on Android. Each PSX RGB555 word is
 * expanded before upload to R=low byte, G=high byte, B=0, A=255. Sampling .rg
 * therefore reconstructs the exact original 16-bit word even on drivers that
 * mishandle the second channel of an RG8 upload. */
#\tdefine VRAM_FORMAT            GL_RGBA
#\tdefine VRAM_INTERNAL_FORMAT   GL_RGBA8
#elif defined(RENDERER_OGLES)
#\tdefine VRAM_FORMAT            GL_LUMINANCE_ALPHA
#\tdefine VRAM_INTERNAL_FORMAT   GL_LUMINANCE_ALPHA
#endif
""",
        "use RGBA8 transport VRAM on Android GLES3",
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


def patch_android_vram_upload() -> None:
    replace_once(
        RENDER,
        """unsigned short vram[VRAM_WIDTH * VRAM_HEIGHT];

void GR_ResetDevice()
""",
        """unsigned short vram[VRAM_WIDTH * VRAM_HEIGHT];

#if defined(__ANDROID__)
/* RGBA8 upload staging. The renderer still decodes the first two sampled
 * channels as the low/high bytes of one PSX RGB555 word. Expanding explicitly
 * avoids mobile-driver channel loss and makes byte order unambiguous. */
static unsigned char s_androidVramRGBA[VRAM_WIDTH * VRAM_HEIGHT * 4];

static void GR_ExpandVramWordsToRGBA(const unsigned short* src,
                                     unsigned char* dst,
                                     size_t pixelCount)
{
    for (size_t i = 0; i < pixelCount; i++)
    {
        const unsigned short word = src[i];
        dst[i * 4 + 0] = (unsigned char)(word & 0xFF);
        dst[i * 4 + 1] = (unsigned char)(word >> 8);
        dst[i * 4 + 2] = 0;
        dst[i * 4 + 3] = 255;
    }
}
#endif

void GR_ResetDevice()
""",
        "add Android PSX-word RGBA expansion",
    )

    replace_once(
        RENDER,
        """#if defined(RENDERER_OGL)
\tglTexImage2D(GL_TEXTURE_2D, 0, VRAM_INTERNAL_FORMAT, VRAM_WIDTH, VRAM_HEIGHT, 0, VRAM_FORMAT, GL_UNSIGNED_BYTE, vram);
#else
\tglTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, VRAM_WIDTH, VRAM_HEIGHT, VRAM_FORMAT, GL_UNSIGNED_BYTE, vram);
#endif
""",
        """#if defined(__ANDROID__)
\tGR_ExpandVramWordsToRGBA(vram, s_androidVramRGBA,
\t                         (size_t)VRAM_WIDTH * (size_t)VRAM_HEIGHT);
\tglTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, VRAM_WIDTH, VRAM_HEIGHT,
\t                GL_RGBA, GL_UNSIGNED_BYTE, s_androidVramRGBA);
#elif defined(RENDERER_OGL)
\tglTexImage2D(GL_TEXTURE_2D, 0, VRAM_INTERNAL_FORMAT, VRAM_WIDTH, VRAM_HEIGHT, 0, VRAM_FORMAT, GL_UNSIGNED_BYTE, vram);
#else
\tglTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, VRAM_WIDTH, VRAM_HEIGHT, VRAM_FORMAT, GL_UNSIGNED_BYTE, vram);
#endif
""",
        "expand full Android VRAM upload to RGBA8",
    )

    replace_once(
        RENDER,
        """\tfor (int i = 0; i < 2; i++)
\t{
\t\tglBindTexture(GL_TEXTURE_2D, g_vramTexturesDouble[i]);
\t\tglTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, VRAM_FORMAT, GL_UNSIGNED_BYTE, block);
\t}
\tglBindTexture(GL_TEXTURE_2D, g_lastBoundTexture);

\tfree(block);
""",
        """#if defined(__ANDROID__)
\tunsigned char* rgbaBlock = (unsigned char*)malloc((size_t)w * (size_t)h * 4u);
\tif (!rgbaBlock)
\t{
\t\tfree(block);
\t\treturn;
\t}
\tGR_ExpandVramWordsToRGBA(block, rgbaBlock, (size_t)w * (size_t)h);
#endif

\tfor (int i = 0; i < 2; i++)
\t{
\t\tglBindTexture(GL_TEXTURE_2D, g_vramTexturesDouble[i]);
#if defined(__ANDROID__)
\t\tglTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, GL_RGBA, GL_UNSIGNED_BYTE, rgbaBlock);
#else
\t\tglTexSubImage2D(GL_TEXTURE_2D, 0, x, y, w, h, VRAM_FORMAT, GL_UNSIGNED_BYTE, block);
#endif
\t}
\tglBindTexture(GL_TEXTURE_2D, g_lastBoundTexture);

#if defined(__ANDROID__)
\tfree(rgbaBlock);
#endif
\tfree(block);
""",
        "expand direct Android VRAM-region uploads to RGBA8",
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
    patch_android_vram_upload()
    patch_shared_draw_trace()
    print("Android GLES RGBA VRAM and ordering-table fixes applied successfully.")
