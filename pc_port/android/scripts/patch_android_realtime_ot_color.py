#!/usr/bin/env python3
"""Make the Android renderer real-time and remove the red textured-scene tint.

The previous diagnostic guard parsed /proc/self/maps and formatted a crash string
for essentially every PSX primitive. Besides producing false OT_INVALID_NEXT
reports when the fixed range table missed a valid Android mapping, that work ran
thousands of times per frame and starved audio/rendering.

Keep only cheap architectural pointer sanity checks during normal rendering. The
original linked-list safety cap and native signal handler remain active.

The boot logos use neutral/untextured colour, while cutscenes and the 3D world
multiply texture samples by GTE vertex RGB. On this Android path those lighting
channels are red-dominant even though the underlying texture/CLUT is now valid.
Use the strongest lighting component as a neutral intensity for textured prims
only. Untextured coloured prims keep their original RGB, so flat logos/UI are not
turned grey. This is an Android compatibility fallback until the GTE colour
pipeline itself is made bit-exact on ARM64.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
GPU = PSYCROSS / "src" / "gpu" / "PsyX_GPU.cpp"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"


def regex_once(path: Path, pattern: str, replacement: str, marker: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"[already applied] {label}")
        return
    updated, count = re.subn(
        pattern,
        lambda _match: replacement,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(updated, encoding="utf-8")
    print(f"[applied] {label}")


def replace_once(path: Path, old: str, new: str, marker: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"[already applied] {label}")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[applied] {label}")


def patch_realtime_ot_guard() -> None:
    regex_once(
        GPU,
        r'''struct AndroidReadableRange\n\{.*?\nstatic int AndroidExpectedPrimitiveLength''',
        r'''/* The original diagnostic walked /proc/self/maps for every OT node and
 * primitive. That was both incomplete (a fixed 512-entry snapshot can miss a
 * valid Android mapping) and far too expensive for a 30 fps game. Keep only
 * cheap canonical-address/overflow checks here; the original one-million-node
 * safety cap and installed SIGSEGV/SIGBUS handlers still catch real corruption. */
static int AndroidPointerReadable(const void* pointer, size_t length)
{
\tconst uintptr_t start = (uintptr_t)pointer;
\tuintptr_t end;
\tif (!pointer || length == 0 || start > UINTPTR_MAX - length)
\t\treturn 0;
\tend = start + length;
\treturn start >= 0x10000ULL && end > start && end < 0x800000000000ULL;
}

/* Normal rendering must not snprintf/copy a diagnostic for every primitive. */
static void AndroidSetOtContext(const char* stage, uintptr_t node,
                                uintptr_t packet, int length, int code)
{
\t(void)stage; (void)node; (void)packet; (void)length; (void)code;
}

/* Error-only path: retain the exact packet context in the launcher report. */
static void AndroidRejectOt(const char* status, const char* stage,
                            uintptr_t node, uintptr_t packet,
                            int length, int code)
{
\tchar report[192];
\tsnprintf(report, sizeof(report),
\t         "%s|%s node=%llx packet=%llx len=%d code=%02x",
\t         status, stage,
\t         (unsigned long long)node,
\t         (unsigned long long)packet,
\t         length, code & 0xFF);
\tPcPort_WriteStartupStatus(report);
}

static int AndroidExpectedPrimitiveLength''',
        "Normal rendering must not snprintf",
        "replace per-primitive maps/tracing with cheap OT sanity checks",
    )


def patch_android_texture_lighting() -> None:
    replace_once(
        RENDER,
        '''#define GTE_VERTEX_SHADER \\
''',
        '''#if defined(__ANDROID__)
/* Android ARM64 compatibility: the base texture/CLUT is correct (logos render
 * correctly), but GTE-lit textured primitives arrive red-dominant. bright==2
 * identifies textured primitives; bright==1 is the untextured/flat path. Use a
 * neutral intensity only for textures so coloured flat logos/UI remain intact. */
#define GTE_ANDROID_VERTEX_COLOR \\
\t\t"\t\tfloat androidLight = max(a_color.r, max(a_color.g, a_color.b));\n"\\
\t\t"\t\tfloat androidTextured = step(1.5, a_texcoord.z);\n"\\
\t\t"\t\tvec3 androidRgb = mix(a_color.rgb * a_texcoord.z, vec3(androidLight * a_texcoord.z), androidTextured);\n"\\
\t\t"\t\tv_color = vec4(androidRgb, a_color.a);\n"
#else
#define GTE_ANDROID_VERTEX_COLOR \\
\t\t"\t\tv_color = a_color;\n"\\
\t\t"\t\tv_color.xyz *= a_texcoord.z;\n"
#endif

#define GTE_VERTEX_SHADER \\
''',
        "GTE_ANDROID_VERTEX_COLOR",
        "add Android-only neutral textured-lighting fallback",
    )

    replace_once(
        RENDER,
        '''\t"\t\tv_color = a_color;\n"\\
\t"\t\tv_color.xyz *= a_texcoord.z;\n"\\
''',
        '''\tGTE_ANDROID_VERTEX_COLOR\\
''',
        "\tGTE_ANDROID_VERTEX_COLOR\\\n",
        "route vertex colour through Android compatibility macro",
    )


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_realtime_ot_guard()
    patch_android_texture_lighting()
    print("Android real-time OT and neutral texture-lighting fixes applied successfully.")
