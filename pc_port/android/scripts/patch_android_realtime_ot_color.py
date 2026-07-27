#!/usr/bin/env python3
"""Make the Android renderer real-time and remove the red textured-scene tint."""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
GPU = PSYCROSS / "src" / "gpu" / "PsyX_GPU.cpp"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"

OT_MARKER = "Normal rendering must not snprintf/copy a diagnostic"
COLOR_USE = "\tGTE_ANDROID_VERTEX_COLOR\\"
COLOR_DEF = "#define GTE_ANDROID_VERTEX_COLOR"


def patch_realtime_ot_guard() -> None:
    text = GPU.read_text(encoding="utf-8")
    if OT_MARKER in text:
        print("[already applied] real-time OT guard")
        return

    start = text.find("struct AndroidReadableRange")
    end = text.find("static int AndroidExpectedPrimitiveLength", start)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("real-time OT guard: Android readable-range block not found")

    replacement = r'''/* The original diagnostic walked /proc/self/maps for every OT node and
 * primitive. That was both incomplete and far too expensive for a real-time
 * game. Keep only cheap canonical-address and overflow checks here. */
static int AndroidPointerReadable(const void* pointer, size_t length)
{
	const uintptr_t start = (uintptr_t)pointer;
	uintptr_t end;
	if (!pointer || length == 0 || start > UINTPTR_MAX - length)
		return 0;
	end = start + length;
	return start >= 0x10000ULL && end > start && end < 0x800000000000ULL;
}

/* Normal rendering must not snprintf/copy a diagnostic for every primitive. */
static void AndroidSetOtContext(const char* stage, uintptr_t node,
                                uintptr_t packet, int length, int code)
{
	(void)stage;
	(void)node;
	(void)packet;
	(void)length;
	(void)code;
}

/* Error-only path: retain exact packet context in the launcher report. */
static void AndroidRejectOt(const char* status, const char* stage,
                            uintptr_t node, uintptr_t packet,
                            int length, int code)
{
	char report[192];
	snprintf(report, sizeof(report),
	         "%s|%s node=%llx packet=%llx len=%d code=%02x",
	         status, stage,
	         (unsigned long long)node,
	         (unsigned long long)packet,
	         length, code & 0xFF);
	PcPort_WriteStartupStatus(report);
}

'''

    GPU.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("[applied] replace per-primitive maps/tracing with cheap OT checks")


def patch_android_texture_lighting() -> None:
    text = RENDER.read_text(encoding="utf-8")
    anchor = "#define GTE_VERTEX_SHADER \\"
    anchor_pos = text.find(anchor)
    if anchor_pos < 0:
        raise RuntimeError("texture lighting: GTE vertex shader anchor not found")

    if COLOR_USE not in text:
        prefix = text[:anchor_pos]
        lines = text[anchor_pos:].splitlines(keepends=True)
        matches = []
        for index in range(len(lines) - 1):
            if ("v_color = a_color;" in lines[index] and
                    "v_color.xyz *= a_texcoord.z;" in lines[index + 1]):
                matches.append(index)
        if len(matches) != 1:
            raise RuntimeError(
                f"texture lighting: expected one original v_color pair, found {len(matches)}"
            )
        index = matches[0]
        indent = lines[index][: len(lines[index]) - len(lines[index].lstrip(" \t"))]
        lines[index:index + 2] = [indent + "GTE_ANDROID_VERTEX_COLOR\\\n"]
        text = prefix + "".join(lines)
        print("[applied] route vertex colour through Android compatibility macro")
    else:
        print("[already applied] Android vertex-colour macro use")

    macro_block = r'''#if defined(__ANDROID__)
/* Android ARM64 compatibility fallback. The base texture/CLUT path is valid,
 * but GTE-lit textured primitives can arrive red-dominant. bright==2 marks the
 * textured path; use its strongest lighting component as neutral intensity.
 * Untextured coloured primitives keep their original RGB. */
#define GTE_ANDROID_VERTEX_COLOR \
		"		float androidLight = max(a_color.r, max(a_color.g, a_color.b));\n"\
		"		float androidTextured = step(1.5, a_texcoord.z);\n"\
		"		vec3 androidRgb = mix(a_color.rgb * a_texcoord.z, vec3(androidLight * a_texcoord.z), androidTextured);\n"\
		"		v_color = vec4(androidRgb, a_color.a);\n"
#else
#define GTE_ANDROID_VERTEX_COLOR \
		"		v_color = a_color;\n"\
		"		v_color.xyz *= a_texcoord.z;\n"
#endif

'''

    if COLOR_DEF not in text:
        anchor_pos = text.find(anchor)
        text = text[:anchor_pos] + macro_block + text[anchor_pos:]
        print("[applied] add Android-only neutral textured-lighting macro")
    else:
        print("[already applied] Android textured-lighting macro")

    if text.count(COLOR_USE) != 1:
        raise RuntimeError(
            f"texture lighting: macro use count is {text.count(COLOR_USE)}, expected 1"
        )

    RENDER.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_realtime_ot_guard()
    patch_android_texture_lighting()
    print("Android real-time OT and neutral texture-lighting fixes applied successfully.")
