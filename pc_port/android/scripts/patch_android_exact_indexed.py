#!/usr/bin/env python3
"""Install an Android GLES3 integer VRAM/CLUT sampler robustly.

The patch is applied to the pinned PsyCross checkout during GitHub Actions.  It
uses structural macro boundaries instead of depending on indentation or on a
particular previously generated Android fetch block.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"


def remove_per_draw_file_io() -> None:
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


def patch_rgba_transport() -> None:
    text = RENDER.read_text(encoding="utf-8")

    if "const unsigned char high = (unsigned char)(word >> 8);" not in text:
        assignment_pattern = re.compile(
            r"(?P<indent>[ \t]*)dst\[i \* 4 \+ 0\] = \(unsigned char\)\(word & 0xFF\);\n"
            r"(?P=indent)dst\[i \* 4 \+ 1\] = \(unsigned char\)\(word >> 8\);\n"
            r"(?P=indent)dst\[i \* 4 \+ 2\] = 0;\n"
            r"(?P=indent)dst\[i \* 4 \+ 3\] = 255;"
        )

        def expand(match: re.Match[str]) -> str:
            indent = match.group("indent")
            return (
                f"{indent}const unsigned char low = (unsigned char)(word & 0xFF);\n"
                f"{indent}const unsigned char high = (unsigned char)(word >> 8);\n"
                f"{indent}dst[i * 4 + 0] = low;\n"
                f"{indent}dst[i * 4 + 1] = high;\n"
                f"{indent}dst[i * 4 + 2] = high;\n"
                f"{indent}dst[i * 4 + 3] = high;"
            )

        text, count = assignment_pattern.subn(expand, text, count=1)
        if count != 1:
            raise RuntimeError(
                f"RGBA transport: expected one PSX-word expansion block, found {count}"
            )
        print("[applied] replicate the high PSX byte across G/B/A")
    else:
        print("[already applied] replicate the high PSX byte across G/B/A")

    old_pack = '"\\tfragColor = vec4(lo / 255.0, hi / 255.0, 0.0, 1.0);\\n"'
    new_pack = '"\\tfragColor = vec4(lo / 255.0, hi / 255.0, hi / 255.0, hi / 255.0);\\n"'
    if old_pack in text:
        text = text.replace(old_pack, new_pack, 1)
        print("[applied] keep feedback packing consistent with RGBA transport")
    elif new_pack in text:
        print("[already applied] keep feedback packing consistent with RGBA transport")
    else:
        print("[not present] framebuffer feedback packing shader")

    begin = text.find("void GR_BeginScene()")
    if begin < 0:
        raise RuntimeError("RGBA mask: GR_BeginScene was not found")
    use_gl = text.find("#if USE_OPENGL", begin)
    if use_gl < 0:
        raise RuntimeError("RGBA mask: GR_BeginScene OpenGL block was not found")
    mask = "#ifdef __ANDROID__\n\tglColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);\n#endif\n"
    scene_end = text.find("void GR_EndScene()", begin)
    if mask not in text[begin:scene_end]:
        insert_at = use_gl + len("#if USE_OPENGL\n")
        text = text[:insert_at] + mask + text[insert_at:]
        print("[applied] restore all framebuffer colour channels each scene")
    else:
        print("[already applied] restore all framebuffer colour channels each scene")

    RENDER.write_text(text, encoding="utf-8")


def replace_fetch_block(text: str) -> str:
    if "ivec2 VRAMBytesAt(vec2 pixel)" in text:
        print("[already applied] exact integer VRAM fetch")
        return text

    original_start = text.find("#if (VRAM_FORMAT == GL_LUMINANCE_ALPHA)")
    android_start = text.find("#if defined(__ANDROID__)\n#define GPU_FETCH_VRAM_FUNC")
    start_candidates = [value for value in (original_start, android_start) if value >= 0]
    if not start_candidates:
        raise RuntimeError("exact VRAM fetch: conditional block start was not found")
    start = min(start_candidates)

    end_marker = "\n\n/* PGXP path"
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError("exact VRAM fetch: PGXP boundary was not found")

    exact = r'''#if defined(__ANDROID__)
#define GPU_FETCH_VRAM_FUNC\
        "\tuniform sampler2D s_texture;\n"\
        "\tivec2 VRAMBytesAt(vec2 pixel) {\n"\
        "\t\tivec2 p = clamp(ivec2(floor(pixel)), ivec2(0), ivec2(1023, 511));\n"\
        "\t\tvec4 raw = texelFetch(s_texture, p, 0);\n"\
        "\t\tint lo = int(floor(raw.r * 255.0 + 0.5));\n"\
        "\t\tint hi = int(floor(max(raw.g, max(raw.b, raw.a)) * 255.0 + 0.5));\n"\
        "\t\treturn ivec2(lo, hi);\n"\
        "\t}\n"\
        "\tint VRAMWordAt(vec2 pixel) { ivec2 b = VRAMBytesAt(pixel); return b.x | (b.y << 8); }\n"\
        "\tvec2 VRAM(vec2 uv) { return vec2(VRAMBytesAt(uv * vec2(1024.0, 512.0))) * (1.0 / 255.0); }\n"
#elif (VRAM_FORMAT == GL_LUMINANCE_ALPHA)
#define GPU_FETCH_VRAM_FUNC\
        "\tuniform sampler2D s_texture;\n"\
        "\tvec2 VRAM(vec2 uv) { return floor(texture2D(s_texture, uv).ra * 255.0 + 0.5) * (1.0 / 255.0); }\n"
#else
#define GPU_FETCH_VRAM_FUNC\
        "\tuniform sampler2D s_texture;\n"\
        "\tvec2 VRAM(vec2 uv) { return floor(texture2D(s_texture, uv).rg * 255.0 + 0.5) * (1.0 / 255.0); }\n"
#endif'''

    print("[applied] replace VRAM fetch conditional with Android texelFetch path")
    return text[:start] + exact + text[end:]


def wrap_macro(text: str, name: str, next_name: str, android_body: str) -> str:
    marker = f"ANDROID_EXACT_{name}"
    if marker in text:
        print(f"[already applied] exact {name}")
        return text

    start = text.find(f"#define {name}")
    end = text.find(f"#define {next_name}", start + 1)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(
            f"exact {name}: structural boundaries were not found (start={start}, end={end})"
        )

    original = text[start:end].rstrip() + "\n"
    replacement = (
        f"#if defined(__ANDROID__)\n#define {marker} 1\n"
        f"{android_body.rstrip()}\n#else\n{original}#endif\n\n"
    )
    print(f"[applied] exact integer {name}")
    return text[:start] + replacement + text[end:]


def patch_exact_indexed_shaders() -> None:
    text = RENDER.read_text(encoding="utf-8")
    text = replace_fetch_block(text)

    sample4 = r'''#define GPU_SAMPLE_TEXTURE_4BIT_FUNC\
        "\tfloat samplePSX(vec2 tc) {\n"\
        "\t\tivec2 p = ivec2(floor(tc));\n"\
        "\t\tint packed = VRAMWordAt(v_page_clut.xy + vec2(float(p.x >> 2), float(p.y)));\n"\
        "\t\tint index = (packed >> ((p.x & 3) * 4)) & 15;\n"\
        "\t\tvec2 clutPixel = v_page_clut.zw * vec2(1024.0, 512.0) + vec2(float(index), 0.0);\n"\
        "\t\treturn float(VRAMWordAt(clutPixel));\n"\
        "\t}\n"'''
    sample8 = r'''#define GPU_SAMPLE_TEXTURE_8BIT_FUNC\
        "\tfloat samplePSX(vec2 tc) {\n"\
        "\t\tivec2 p = ivec2(floor(tc));\n"\
        "\t\tint packed = VRAMWordAt(v_page_clut.xy + vec2(float(p.x >> 1), float(p.y)));\n"\
        "\t\tint index = ((p.x & 1) == 0) ? (packed & 255) : ((packed >> 8) & 255);\n"\
        "\t\tvec2 clutPixel = v_page_clut.zw * vec2(1024.0, 512.0) + vec2(float(index), 0.0);\n"\
        "\t\treturn float(VRAMWordAt(clutPixel));\n"\
        "\t}\n"'''
    sample16 = r'''#define GPU_SAMPLE_TEXTURE_16BIT_FUNC\
        "\tfloat samplePSX(vec2 tc) {\n"\
        "\t\tivec2 p = ivec2(floor(tc));\n"\
        "\t\treturn float(VRAMWordAt(v_page_clut.xy + vec2(p)));\n"\
        "\t}\n"'''

    text = wrap_macro(text, "GPU_SAMPLE_TEXTURE_4BIT_FUNC", "GPU_SAMPLE_TEXTURE_8BIT_FUNC", sample4)
    text = wrap_macro(text, "GPU_SAMPLE_TEXTURE_8BIT_FUNC", "GPU_SAMPLE_TEXTURE_16BIT_FUNC", sample8)
    text = wrap_macro(text, "GPU_SAMPLE_TEXTURE_16BIT_FUNC", "GPU_BILINEAR_SAMPLE_FUNC", sample16)

    required = (
        "ivec2 VRAMBytesAt(vec2 pixel)",
        "ANDROID_EXACT_GPU_SAMPLE_TEXTURE_4BIT_FUNC",
        "ANDROID_EXACT_GPU_SAMPLE_TEXTURE_8BIT_FUNC",
        "ANDROID_EXACT_GPU_SAMPLE_TEXTURE_16BIT_FUNC",
        "texelFetch(s_texture, p, 0)",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise RuntimeError(f"exact indexed shader verification failed: {missing}")

    RENDER.write_text(text, encoding="utf-8")
    print("Android integer VRAM/CLUT shader source verified.")


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    remove_per_draw_file_io()
    patch_rgba_transport()
    patch_exact_indexed_shaders()
    print("Android exact indexed-texture patch applied successfully.")
