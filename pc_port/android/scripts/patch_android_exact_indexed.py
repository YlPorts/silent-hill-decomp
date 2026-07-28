#!/usr/bin/env python3
"""Use an exact GLES3 VRAM/CLUT path and remove render-loop diagnostics.

The Konami/KCET logos use direct-colour data and already render correctly, while
FMV frames, menus, and most world textures use 4/8-bit indexed PSX textures.
The desktop shader extracts those indices with normalised floating-point math.
On the affected Android GLES driver that path corrupts CLUT lookups.

For Android GLES3, fetch VRAM texels with texelFetch and perform 4/8-bit index
extraction with integer bit operations. Desktop and non-Android GLES retain the
original shader strings. Also remove status-file writes from every GsDrawOt;
those writes run many times per frame and can stall both rendering and audio.
"""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"
LIBGS = PC_PORT / "src" / "stubs" / "libgs_stub.c"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new and new in text:
        print(f"[already applied] {label}")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[applied] {label}")


def remove_per_draw_file_io() -> None:
    text = LIBGS.read_text(encoding="utf-8")
    for stage in ("FIRST_FRAME_DEPTH_CLEAR", "FIRST_FRAME_PARSE_OT"):
        line = f'        PcPort_WriteStartupStatus("{stage}");\n'
        count = text.count(line)
        if count == 1:
            text = text.replace(line, "", 1)
            print(f"[applied] remove per-draw status {stage}")
        elif count == 0:
            print(f"[already applied] remove per-draw status {stage}")
        else:
            raise RuntimeError(f"remove {stage}: found {count} matches")
    LIBGS.write_text(text, encoding="utf-8")


def patch_rgba_transport() -> None:
    # Preserve the high PSX byte redundantly. texelFetch reads G first, while B/A
    # provide a safe fallback on drivers that return one secondary channel as 0.
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
        dst[i * 4 + 1] = high;
        dst[i * 4 + 2] = high;
        dst[i * 4 + 3] = high;
""",
        "replicate the PSX high byte in Android RGBA transport",
    )

    # Framebuffer->VRAM feedback must use the same byte layout as CPU uploads.
    old_pack = '"\\tfragColor = vec4(lo / 255.0, hi / 255.0, 0.0, 1.0);\\n"\n'
    new_pack = '"\\tfragColor = vec4(lo / 255.0, hi / 255.0, hi / 255.0, hi / 255.0);\\n"\n'
    text = RENDER.read_text(encoding="utf-8")
    if old_pack in text:
        text = text.replace(old_pack, new_pack, 1)
        RENDER.write_text(text, encoding="utf-8")
        print("[applied] keep framebuffer-feedback byte layout consistent")
    elif new_pack in text:
        print("[already applied] keep framebuffer-feedback byte layout consistent")
    else:
        print("[not present] framebuffer-feedback pack shader")

    # Defensive reset for a driver/state leak that can leave only one channel writable.
    replace_once(
        RENDER,
        """#if USE_OPENGL
#ifdef RENDERER_OGLES
\tglClearDepthf(1.0f);
""",
        """#if USE_OPENGL
#ifdef __ANDROID__
\tglColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
#endif
#ifdef RENDERER_OGLES
\tglClearDepthf(1.0f);
""",
        "restore RGBA writes at the start of every Android scene",
    )


def patch_exact_indexed_shaders() -> None:
    text = RENDER.read_text(encoding="utf-8")

    exact_fetch = r'''#if defined(__ANDROID__)
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
'''

    if "ivec2 VRAMBytesAt(vec2 pixel)" not in text:
        # Support either the untouched PsyCross conditional or an earlier Android
        # branch inserted by a previous diagnostic patch.
        android_start = text.find("#if defined(__ANDROID__)\n#define GPU_FETCH_VRAM_FUNC\\")
        android_end = text.find("#elif (VRAM_FORMAT == GL_LUMINANCE_ALPHA)", android_start)
        if android_start >= 0 and android_end > android_start:
            text = text[:android_start] + exact_fetch + text[android_end:]
        else:
            original_if = "#if (VRAM_FORMAT == GL_LUMINANCE_ALPHA)"
            original_start = text.find(original_if)
            if original_start < 0:
                raise RuntimeError("exact VRAM fetch: original conditional not found")
            original_tail = text[original_start:].replace(
                original_if,
                "#elif (VRAM_FORMAT == GL_LUMINANCE_ALPHA)",
                1,
            )
            text = text[:original_start] + exact_fetch + original_tail
        print("[applied] use texelFetch for exact Android VRAM bytes")
    else:
        print("[already applied] use texelFetch for exact Android VRAM bytes")

    def wrap_macro(name: str, next_name: str, android_body: str) -> None:
        nonlocal text
        marker = f"ANDROID_EXACT_{name}"
        if marker in text:
            print(f"[already applied] exact {name}")
            return
        start_marker = f"#define {name}\\"
        end_marker = f"#define {next_name}\\"
        start = text.find(start_marker)
        end = text.find(end_marker, start + len(start_marker))
        if start < 0 or end < 0:
            raise RuntimeError(f"exact {name}: macro boundaries not found")
        original = text[start:end].rstrip() + "\n"
        replacement = (
            f"#if defined(__ANDROID__)\n#define ANDROID_EXACT_{name} 1\n"
            f"{android_body}\n#else\n{original}#endif\n\n"
        )
        text = text[:start] + replacement + text[end:]
        print(f"[applied] exact {name}")

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

    wrap_macro("GPU_SAMPLE_TEXTURE_4BIT_FUNC", "GPU_SAMPLE_TEXTURE_8BIT_FUNC", sample4)
    wrap_macro("GPU_SAMPLE_TEXTURE_8BIT_FUNC", "GPU_SAMPLE_TEXTURE_16BIT_FUNC", sample8)
    wrap_macro("GPU_SAMPLE_TEXTURE_16BIT_FUNC", "GPU_BILINEAR_SAMPLE_FUNC", sample16)

    RENDER.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    remove_per_draw_file_io()
    patch_rgba_transport()
    patch_exact_indexed_shaders()
    print("Android exact indexed-texture and real-time render fixes applied successfully.")
