#!/usr/bin/env python3
"""Harden Android colour output and the PsyCross ordering-table walker.

This script runs after the existing Android startup/GLES patches. It keeps the
PSX high colour byte redundantly in G/B/A, restores the full framebuffer colour
mask, and adds Android readable-memory checks around OT linked-list traversal.
It also keeps an in-memory primitive context that the native signal handler can
persist without performing file I/O for every primitive.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
MAIN_PC = PC_PORT / "src" / "main_pc.c"
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"
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


def regex_once(path: Path, pattern: str, replacement: str, marker: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"[already applied] {label}")
        return
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: regex matched {count} times in {path}")
    path.write_text(updated, encoding="utf-8")
    print(f"[applied] {label}")


def patch_crash_context() -> None:
    replace_once(
        MAIN_PC,
        "static void PcPort_CrashSignalHandler(int sig)\n",
        """static char s_PcPortCrashContext[192] = "NO_CONTEXT";

void PcPort_SetCrashContext(const char* context)
{
    size_t length;
    if (context == NULL)
        context = "NO_CONTEXT";
    length = strlen(context);
    if (length >= sizeof(s_PcPortCrashContext))
        length = sizeof(s_PcPortCrashContext) - 1;
    memcpy(s_PcPortCrashContext, context, length);
    s_PcPortCrashContext[length] = '\0';
}

static void PcPort_CrashSignalHandler(int sig)
""",
        "add persistent native crash context",
    )

    regex_once(
        MAIN_PC,
        r"static void PcPort_CrashSignalHandler\(int sig\)\n\{.*?\n\}\n\nstatic void PcPort_InstallCrashHandlers",
        r'''static void PcPort_CrashSignalHandler(int sig)
{
    const char* signalName = "CRASH_SIGNAL";
    size_t signalLength;
    size_t contextLength = 0;
    int fd;

    switch (sig)
    {
        case SIGSEGV: signalName = "CRASH_SIGSEGV"; break;
        case SIGABRT: signalName = "CRASH_SIGABRT"; break;
        case SIGBUS:  signalName = "CRASH_SIGBUS";  break;
        case SIGILL:  signalName = "CRASH_SIGILL";  break;
        case SIGFPE:  signalName = "CRASH_SIGFPE";  break;
        default: break;
    }

    signalLength = strlen(signalName);
    while (contextLength + 1 < sizeof(s_PcPortCrashContext) &&
           s_PcPortCrashContext[contextLength] != '\0')
        contextLength++;

    fd = open("android_startup_status.txt", O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0)
    {
        write(fd, signalName, signalLength);
        write(fd, "|", 1);
        write(fd, s_PcPortCrashContext, contextLength);
        write(fd, "\n", 1);
        close(fd);
    }
    _exit(128 + sig);
}

static void PcPort_InstallCrashHandlers''',
        "s_PcPortCrashContext",
        "persist signal plus primitive context",
    )


def patch_colour_transport() -> None:
    replace_once(
        RENDER,
        """        dst[i * 4 + 0] = (unsigned char)(word & 0xFF);
        dst[i * 4 + 1] = (unsigned char)(word >> 8);
        dst[i * 4 + 2] = 0;
        dst[i * 4 + 3] = 255;
""",
        """        const unsigned char low = (unsigned char)(word & 0xFF);
        const unsigned char high = (unsigned char)(word >> 8);
        dst[i * 4 + 0] = low;
        /* Keep the high PSX byte redundantly in every remaining channel. Some
         * mobile GLES drivers/devices have shown one secondary channel stuck at
         * zero. The shader selects the largest of G/B/A, so any surviving copy
         * reconstructs the exact RGB555 word. */
        dst[i * 4 + 1] = high;
        dst[i * 4 + 2] = high;
        dst[i * 4 + 3] = high;
""",
        "replicate the high PSX byte across RGBA transport",
    )

    regex_once(
        RENDER,
        r"#if \(VRAM_FORMAT == GL_LUMINANCE_ALPHA\)\n#define GPU_FETCH_VRAM_FUNC\\.*?#endif",
        r'''#if defined(__ANDROID__)
#define GPU_FETCH_VRAM_FUNC\
        "\tuniform sampler2D s_texture;\n"\
        "\tvec2 VRAM(vec2 uv) { vec4 raw = texture2D(s_texture, uv); float highByte = max(raw.g, max(raw.b, raw.a)); return floor(vec2(raw.r, highByte) * 255.0 + 0.5) * (1.0 / 255.0); }\n"
#elif (VRAM_FORMAT == GL_LUMINANCE_ALPHA)
#define GPU_FETCH_VRAM_FUNC\
        "\tuniform sampler2D s_texture;\n"\
        "\tvec2 VRAM(vec2 uv) { return floor(texture2D(s_texture, uv).ra * 255.0 + 0.5) * (1.0 / 255.0); }\n"
#else
#define GPU_FETCH_VRAM_FUNC\
        "\tuniform sampler2D s_texture;\n"\
        "\tvec2 VRAM(vec2 uv) { return floor(texture2D(s_texture, uv).rg * 255.0 + 0.5) * (1.0 / 255.0); }\n"
#endif''',
        "highByte = max(raw.g",
        "read redundant Android high-byte channels",
    )

    replace_once(
        RENDER,
        '"\tfragColor = vec4(lo / 255.0, hi / 255.0, 0.0, 1.0);\\n"\n',
        '"\tfragColor = vec4(lo / 255.0, hi / 255.0, hi / 255.0, hi / 255.0);\\n"\n',
        "replicate framebuffer-feedback high byte",
    )

    replace_once(
        RENDER,
        """#if USE_OPENGL
#ifdef RENDERER_OGLES
\tglClearDepthf(1.0f);
""",
        """#if USE_OPENGL
#ifdef __ANDROID__
\t/* Defensive reset: every game frame must be able to write all four output
\t * channels, regardless of state left by a feedback/depth-only pass. */
\tglColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
#endif
#ifdef RENDERER_OGLES
\tglClearDepthf(1.0f);
""",
        "restore the complete Android framebuffer colour mask",
    )

    replace_once(
        RENDER,
        """\tglDisable(GL_STENCIL_TEST);

\tglUseProgram(g_fbPackShader);
""",
        """\tglDisable(GL_STENCIL_TEST);
#ifdef __ANDROID__
\tglColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
#endif

\tglUseProgram(g_fbPackShader);
""",
        "restore RGBA writes for framebuffer-to-VRAM packing",
    )


def patch_runtime_context_calls() -> None:
    replace_once(
        LIBGS,
        """#ifdef __ANDROID__
extern void PcPort_WriteStartupStatus(const char* status);
#endif
""",
        """#ifdef __ANDROID__
extern void PcPort_WriteStartupStatus(const char* status);
extern void PcPort_SetCrashContext(const char* context);
#endif
""",
        "expose crash context to libgs",
    )
    replace_once(
        LIBGS,
        '        PcPort_WriteStartupStatus("FIRST_FRAME_DEPTH_CLEAR");\n',
        '        PcPort_SetCrashContext("GS_DEPTH_CLEAR");\n',
        "stop overwriting persistent status at depth clear",
    )
    replace_once(
        LIBGS,
        '        PcPort_WriteStartupStatus("FIRST_FRAME_PARSE_OT");\n',
        '        PcPort_SetCrashContext("GS_DRAW_OT");\n',
        "stop overwriting persistent status at every OT draw",
    )

    regex_once(
        LIBGPU,
        r"#ifdef __ANDROID__\nextern void PcPort_WriteStartupStatus\(const char\* status\);\nstatic int s_androidFirstOtTrace = 1;\n#define ANDROID_OT_STAGE\(stage\).*?#endif",
        r'''#ifdef __ANDROID__
extern void PcPort_SetCrashContext(const char* context);
#define ANDROID_OT_STAGE(stage) PcPort_SetCrashContext(stage)
#else
#define ANDROID_OT_STAGE(stage) ((void)0)
#endif''',
        "PcPort_SetCrashContext(const char* context)",
        "keep OT trace continuously in memory",
    )
    regex_once(
        LIBGPU,
        r"\n#ifdef __ANDROID__\n\s*s_androidFirstOtTrace = 0;\n#endif",
        "",
        "ANDROID_OT_STAGE(stage) PcPort_SetCrashContext",
        "remove one-frame-only OT trace switch",
    )


def patch_ot_pointer_guards() -> None:
    replace_once(
        GPU,
        """#include <assert.h>
#include <math.h>
#include <string.h>
""",
        """#include <assert.h>
#include <math.h>
#include <string.h>

#ifdef __ANDROID__
#include <stdio.h>
#include <unistd.h>

extern "C" void PcPort_WriteStartupStatus(const char* status);
extern "C" void PcPort_SetCrashContext(const char* context);

struct AndroidReadableRange
{
\tuintptr_t start;
\tuintptr_t end;
};

static AndroidReadableRange s_androidReadableRanges[512];
static int s_androidReadableRangeCount = 0;
static AndroidReadableRange s_androidLastReadableRange = { 0, 0 };

static void AndroidReloadReadableRanges(void)
{
\tFILE* maps = fopen("/proc/self/maps", "r");
\tchar line[256];
\ts_androidReadableRangeCount = 0;
\ts_androidLastReadableRange.start = 0;
\ts_androidLastReadableRange.end = 0;
\tif (!maps)
\t\treturn;
\twhile (fgets(line, sizeof(line), maps) && s_androidReadableRangeCount < 512)
\t{
\t\tunsigned long start = 0, end = 0;
\t\tchar perms[5] = { 0 };
\t\tif (sscanf(line, "%lx-%lx %4s", &start, &end, perms) == 3 && perms[0] == 'r')
\t\t{
\t\t\ts_androidReadableRanges[s_androidReadableRangeCount].start = (uintptr_t)start;
\t\t\ts_androidReadableRanges[s_androidReadableRangeCount].end = (uintptr_t)end;
\t\t\ts_androidReadableRangeCount++;
\t\t}
\t}
\tfclose(maps);
}

static int AndroidPointerReadable(const void* pointer, size_t length)
{
\tuintptr_t start = (uintptr_t)pointer;
\tuintptr_t end;
\tint attempt;
\tif (!pointer || length == 0 || start > UINTPTR_MAX - length)
\t\treturn 0;
\tend = start + length;
\tif (start >= s_androidLastReadableRange.start && end <= s_androidLastReadableRange.end)
\t\treturn 1;
\tfor (attempt = 0; attempt < 2; attempt++)
\t{
\t\tint i;
\t\tif (attempt == 1 || s_androidReadableRangeCount == 0)
\t\t\tAndroidReloadReadableRanges();
\t\tfor (i = 0; i < s_androidReadableRangeCount; i++)
\t\t{
\t\t\tconst AndroidReadableRange range = s_androidReadableRanges[i];
\t\t\tif (start >= range.start && end <= range.end)
\t\t\t{
\t\t\t\ts_androidLastReadableRange = range;
\t\t\t\treturn 1;
\t\t\t}
\t\t}
\t}
\treturn 0;
}

static void AndroidSetOtContext(const char* stage, uintptr_t node,
                                uintptr_t packet, int length, int code)
{
\tchar context[192];
\tsnprintf(context, sizeof(context),
\t         "%s node=%llx packet=%llx len=%d code=%02x",
\t         stage,
\t         (unsigned long long)node,
\t         (unsigned long long)packet,
\t         length, code & 0xFF);
\tPcPort_SetCrashContext(context);
}

static void AndroidRejectOt(const char* status, const char* stage,
                            uintptr_t node, uintptr_t packet,
                            int length, int code)
{
\tAndroidSetOtContext(stage, node, packet, length, code);
\tPcPort_WriteStartupStatus(status);
}

static int AndroidExpectedPrimitiveLength(int code)
{
\tswitch (code & 0xFD)
\t{
\t\tcase 0x20: return 4;  case 0x24: return 7;
\t\tcase 0x28: return 5;  case 0x2C: return 9;
\t\tcase 0x30: return 6;  case 0x34: return 9;
\t\tcase 0x38: return 8;  case 0x3C: return 12;
\t\tcase 0x40: return 3;  case 0x48: return 5;
\t\tcase 0x4C: return 6;  case 0x50: return 4;
\t\tcase 0x58: return 7;  case 0x5C: return 9;
\t\tcase 0x60: return 3;  case 0x64: return 4;
\t\tcase 0x68: return 2;  case 0x70: return 2;
\t\tcase 0x74: return 3;  case 0x78: return 2;
\t\tcase 0x7C: return 3;
\t\tdefault: return 0;
\t}
}
#else
#define AndroidPointerReadable(pointer, length) 1
#define AndroidSetOtContext(stage, node, packet, length, code) ((void)0)
#define AndroidRejectOt(status, stage, node, packet, length, code) ((void)0)
#define AndroidExpectedPrimitiveLength(code) 0
#endif
""",
        "add Android readable-memory OT guards",
    )

    replace_once(
        GPU,
        """\t\tfor (int safety = 0; safety < (1 << 20); safety++)
\t\t{
\t\t\tconst int tagLength = getlen(basePacket);
""",
        """\t\tfor (int safety = 0; safety < (1 << 20); safety++)
\t\t{
#ifdef __ANDROID__
\t\t\tif (!AndroidPointerReadable((const void*)basePacket, sizeof(P_TAG)))
\t\t\t{
\t\t\t\tAndroidRejectOt("OT_INVALID_NODE", "OT_INVALID_NODE", basePacket, basePacket, 0, 0);
\t\t\t\tbreak;
\t\t\t}
#endif
\t\t\tconst int tagLength = getlen(basePacket);
\t\t\tAndroidSetOtContext("OT_NODE", basePacket, basePacket, tagLength,
\t\t\t                    reinterpret_cast<P_TAG*>(basePacket)->code);
""",
        "validate every OT node before reading its tag",
    )

    replace_once(
        GPU,
        """\t\t\tif (tagLength > 0 && tagLength <= 32)
\t\t\t{
\t\t\t\tuintptr_t currentPacket = basePacket;
\t\t\t\tconst uintptr_t endPacket = basePacket + (tagLength + P_LEN) * sizeof(u_int);
""",
        """\t\t\tif (tagLength > 0 && tagLength <= 32)
\t\t\t{
\t\t\t\tconst size_t packetBytes = (size_t)(tagLength + P_LEN) * sizeof(u_int);
#ifdef __ANDROID__
\t\t\t\tif (!AndroidPointerReadable((const void*)basePacket, packetBytes))
\t\t\t\t{
\t\t\t\t\tAndroidRejectOt("OT_INVALID_PACKET", "OT_INVALID_PACKET",
\t\t\t\t\t                basePacket, basePacket, tagLength,
\t\t\t\t\t                reinterpret_cast<P_TAG*>(basePacket)->code);
\t\t\t\t\tbreak;
\t\t\t\t}
#endif
\t\t\t\tuintptr_t currentPacket = basePacket;
\t\t\t\tconst uintptr_t endPacket = basePacket + packetBytes;
""",
        "validate complete OT packets before parsing",
    )

    replace_once(
        GPU,
        """\t\t\t\twhile (currentPacket < endPacket)
\t\t\t\t{
\t\t\t\t\t/* Whole-town mode can submit far more geometry than one
""",
        """\t\t\t\twhile (currentPacket < endPacket)
\t\t\t\t{
\t\t\t\t\tconst size_t remainingBytes = (size_t)(endPacket - currentPacket);
#ifdef __ANDROID__
\t\t\t\t\tif (remainingBytes < sizeof(P_TAG) ||
\t\t\t\t\t    !AndroidPointerReadable((const void*)currentPacket, sizeof(P_TAG)))
\t\t\t\t\t{
\t\t\t\t\t\tAndroidRejectOt("OT_INVALID_PRIMITIVE", "OT_INVALID_PRIMITIVE",
\t\t\t\t\t\t                basePacket, currentPacket, tagLength, 0);
\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t\t{
\t\t\t\t\t\tconst P_TAG* currentTag = reinterpret_cast<const P_TAG*>(currentPacket);
\t\t\t\t\t\tconst int expectedLength = AndroidExpectedPrimitiveLength(currentTag->code);
\t\t\t\t\t\tAndroidSetOtContext("OT_PRIMITIVE", basePacket, currentPacket,
\t\t\t\t\t\t                    currentTag->len, currentTag->code);
\t\t\t\t\t\tif (expectedLength > 0 &&
\t\t\t\t\t\t    (size_t)(expectedLength + P_LEN) * sizeof(u_int) > remainingBytes)
\t\t\t\t\t\t{
\t\t\t\t\t\t\tAndroidRejectOt("OT_TRUNCATED_PRIMITIVE", "OT_TRUNCATED_PRIMITIVE",
\t\t\t\t\t\t\t                basePacket, currentPacket, currentTag->len, currentTag->code);
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\t}
\t\t\t\t\t}
#endif
\t\t\t\t\t/* Whole-town mode can submit far more geometry than one
""",
        "validate each primitive before dispatch",
    )

    replace_once(
        GPU,
        """\t\t\t\t\tprimLength = ParsePrimitive(reinterpret_cast<P_TAG*>(currentPacket));
\t\t\t\t\tif (primLength <= 0) break;
\t\t\t\t\tcurrentPacket += (primLength + P_LEN) * sizeof(u_int);
""",
        """\t\t\t\t\tprimLength = ParsePrimitive(reinterpret_cast<P_TAG*>(currentPacket));
\t\t\t\t\tif (primLength <= 0)
\t\t\t\t\t{
#ifdef __ANDROID__
\t\t\t\t\t\tconst P_TAG* badTag = reinterpret_cast<const P_TAG*>(currentPacket);
\t\t\t\t\t\tAndroidRejectOt("OT_UNHANDLED_PRIMITIVE", "OT_UNHANDLED_PRIMITIVE",
\t\t\t\t\t\t                basePacket, currentPacket, badTag->len, badTag->code);
#endif
\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t\t{
\t\t\t\t\t\tconst size_t advanceBytes = (size_t)(primLength + P_LEN) * sizeof(u_int);
\t\t\t\t\t\tif (advanceBytes > (size_t)(endPacket - currentPacket))
\t\t\t\t\t\t{
#ifdef __ANDROID__
\t\t\t\t\t\t\tconst P_TAG* badTag = reinterpret_cast<const P_TAG*>(currentPacket);
\t\t\t\t\t\t\tAndroidRejectOt("OT_PRIMITIVE_OVERRUN", "OT_PRIMITIVE_OVERRUN",
\t\t\t\t\t\t\t                basePacket, currentPacket, badTag->len, badTag->code);
#endif
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\t}
\t\t\t\t\t\tcurrentPacket += advanceBytes;
\t\t\t\t\t}
""",
        "reject primitive advances outside their packet",
    )

    replace_once(
        GPU,
        """\t\t\tif (nextPtr < 0x10000 ||
\t\t\t    nextPtr == static_cast<uintptr_t>(-1) ||
\t\t\t    nextPtr >= 0x7FFFFFFFFFFFULL) {
""",
        """\t\t\tif (nextPtr < 0x10000 ||
\t\t\t    nextPtr == static_cast<uintptr_t>(-1) ||
\t\t\t    nextPtr >= 0x7FFFFFFFFFFFULL
#ifdef __ANDROID__
\t\t\t    || !AndroidPointerReadable((const void*)nextPtr, sizeof(P_TAG))
#endif
\t\t\t   ) {
#ifdef __ANDROID__
\t\t\t\tAndroidRejectOt("OT_INVALID_NEXT", "OT_INVALID_NEXT",
\t\t\t\t                basePacket, nextPtr, tagLength,
\t\t\t\t                reinterpret_cast<P_TAG*>(basePacket)->code);
#endif
""",
        "validate next OT pointers against readable Android mappings",
    )


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_crash_context()
    patch_colour_transport()
    patch_runtime_context_calls()
    patch_ot_pointer_guards()
    print("Android RGBA channel and ordering-table runtime guards applied successfully.")
