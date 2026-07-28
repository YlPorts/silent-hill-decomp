#!/usr/bin/env python3
"""Apply focused Android ARMv7 runtime fixes after the base GLES patches.

The patch intentionally leaves the ordering-table walker and GrVertex layout
alone.  It fixes Android drawable sizing, offscreen RGB555 writeback, the
mobile polygon-size cull, and OpenAL device initialization.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"
GPU = PSYCROSS / "src" / "gpu" / "PsyX_GPU.cpp"
AUDIO = PSYCROSS / "src" / "audio" / "PsyX_SPUAL.cpp"


def require_once(text: str, needle: str, label: str) -> int:
    count = text.count(needle)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.index(needle)


def patch_drawable_size() -> None:
    text = RENDER.read_text(encoding="utf-8")
    function_anchor = "void GR_BeginScene()"

    if "static void GR_RefreshAndroidDrawableSize(void)" not in text:
        pos = require_once(text, function_anchor, "Android drawable helper anchor")
        helper = r'''#if defined(__ANDROID__)
/* Use the actual EGL drawable. Android system insets and display cutouts can
 * make it differ from the requested SDL window size; viewport and aspect math
 * must follow the drawable or the frame is clipped/offset. */
static void GR_RefreshAndroidDrawableSize(void)
{
    int drawableWidth = 0;
    int drawableHeight = 0;
    if (g_window != NULL)
        SDL_GL_GetDrawableSize(g_window, &drawableWidth, &drawableHeight);
    if (drawableWidth > 0 && drawableHeight > 0 &&
        (drawableWidth != g_windowWidth || drawableHeight != g_windowHeight))
    {
        eprintinfo("Android drawable resized: %dx%d -> %dx%d\n",
                   g_windowWidth, g_windowHeight, drawableWidth, drawableHeight);
        g_windowWidth = drawableWidth;
        g_windowHeight = drawableHeight;
    }
}
#endif

'''
        text = text[:pos] + helper + text[pos:]
        print("[applied] add Android drawable-size helper")
    else:
        print("[already applied] add Android drawable-size helper")

    call = "#if defined(__ANDROID__)\n\tGR_RefreshAndroidDrawableSize();\n#endif\n"
    begin = text.index(function_anchor)
    next_function = text.find("\nvoid ", begin + len(function_anchor))
    if next_function < 0:
        next_function = len(text)
    if call not in text[begin:next_function]:
        match = re.search(r"void GR_BeginScene\(\)\s*\{\s*\n", text[begin:next_function])
        if not match:
            raise RuntimeError("Android drawable call: GR_BeginScene opening brace not found")
        insert_at = begin + match.end()
        text = text[:insert_at] + call + text[insert_at:]
        print("[applied] refresh drawable size before every frame")
    else:
        print("[already applied] refresh drawable size before every frame")

    RENDER.write_text(text, encoding="utf-8")


def patch_rgb555_pack() -> None:
    text = RENDER.read_text(encoding="utf-8")
    marker = "const u_char* rgba = (const u_char*)&c;"
    if marker not in text:
        pattern = re.compile(
            r"(?P<i>[ \t]*)u_char b = \(\(c >> 3\) & 0x1F\);\n"
            r"(?P=i)u_char g = \(\(c >> 11\) & 0x1F\);\n"
            r"(?P=i)u_char r = \(\(c >> 19\) & 0x1F\);\n"
            r"(?P=i)//u_char a = \(\(c >> 24\) & 0x1F\);\n\n"
            r"(?P=i)int a = r == g == b == 0 \? 0 : 1;\n\n"
            r"(?P=i)\*data_dst\+\+ = r \| \(g << 5\) \| \(b << 10\) \| \(a << 15\);"
        )

        def replacement(match: re.Match[str]) -> str:
            i = match.group("i")
            return (
                f"{i}/* glReadPixels(GL_RGBA/UNSIGNED_BYTE) is R,G,B,A byte order.\n"
                f"{i} * Pack the exact PSX RGB555 word explicitly. */\n"
                f"{i}const u_char* rgba = (const u_char*)&c;\n"
                f"{i}u_char r = (u_char)(rgba[0] >> 3);\n"
                f"{i}u_char g = (u_char)(rgba[1] >> 3);\n"
                f"{i}u_char b = (u_char)(rgba[2] >> 3);\n"
                f"{i}int a = (r | g | b) != 0 ? 1 : 0;\n\n"
                f"{i}*data_dst++ = (ushort)(r | (g << 5) | (b << 10) | (a << 15));"
            )

        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"RGB555 pack block: expected one match, found {count}")
        print("[applied] pack framebuffer RGBA into correct PSX RGB555")
    else:
        print("[already applied] pack framebuffer RGBA into correct PSX RGB555")

    if "assert(y + h <= VRAM_HEIGHT);" not in text:
        old = "assert(y + h <= VRAM_WIDTH);"
        require_once(text, old, "VRAM height assertion")
        text = text.replace(old, "assert(y + h <= VRAM_HEIGHT);", 1)
        print("[applied] validate framebuffer copy against VRAM height")
    else:
        print("[already applied] validate framebuffer copy against VRAM height")

    RENDER.write_text(text, encoding="utf-8")


def patch_offscreen_writeback() -> None:
    text = RENDER.read_text(encoding="utf-8")
    function_anchor = "void GR_SetOffscreenState(const RECT16* offscreenRect, int enable)"
    function_pos = require_once(text, function_anchor, "Android offscreen function")

    if "static void GR_AndroidPackOffscreenToVram(void)" not in text:
        helper = r'''#if defined(__ANDROID__)
/* Offscreen scene targets are ordinary RGBA framebuffers, but PSX VRAM stores
 * each pixel as one packed RGB555 word. A raw framebuffer blit writes colour
 * bytes as if they were packed words and produces the red/corrupt cutscenes. */
static void GR_AndroidPackOffscreenToVram(void)
{
    const int aw = g_PreviousOffscreen.w;
    const int ah = g_PreviousOffscreen.h;
    if (aw <= 0 || ah <= 0)
    {
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        return;
    }

    const size_t pixelCount = (size_t)aw * (size_t)ah;
    static u_int* rgbaPixels = NULL;
    static size_t rgbaCapacity = 0;
    if (pixelCount > rgbaCapacity)
    {
        u_int* resized = (u_int*)realloc(rgbaPixels, pixelCount * sizeof(u_int));
        if (resized != NULL)
        {
            rgbaPixels = resized;
            rgbaCapacity = pixelCount;
        }
    }

    if (rgbaPixels == NULL || rgbaCapacity < pixelCount)
    {
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        eprintwarn("Android offscreen RGB555 buffer allocation failed\n");
        return;
    }

    glBindFramebuffer(GL_FRAMEBUFFER, g_glOffscreenFramebuffer);
    glReadPixels(0, 0, aw, ah, GL_RGBA, GL_UNSIGNED_BYTE, rgbaPixels);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);

    GR_CopyRGBAFramebufferToVRAM(rgbaPixels,
        g_PreviousOffscreen.x, g_PreviousOffscreen.y, aw, ah, 0, 1);
    GR_DirectUploadVRAMRegion(g_PreviousOffscreen.x,
        g_PreviousOffscreen.y, aw, ah);
}
#endif

'''
        text = text[:function_pos] + helper + text[function_pos:]
        function_pos += len(helper)
        print("[applied] add Android offscreen RGB555 helper")
    else:
        print("[already applied] add Android offscreen RGB555 helper")
        function_pos = text.index(function_anchor)

    # The legacy <=64 path uploads ushort data using VRAM_FORMAT. After the
    # Android RGBA8 transport patch VRAM_FORMAT is GL_RGBA, so exclude it and
    # route Android through the shared helper in the general branch.
    skip_marker = "ANDROID_SKIP_LEGACY_SMALL_OFFSCREEN"
    if skip_marker not in text:
        small_start = text.find(
            "\t\telse if (g_PreviousOffscreen.w > 0 && g_PreviousOffscreen.h > 0 &&",
            function_pos,
        )
        if small_start < 0:
            raise RuntimeError("Android offscreen: legacy small-scratch branch not found")
        general_else = text.find("\n\t\telse\n\t\t{\n#if USE_OFFSCREEN_BLIT", small_start)
        if general_else < 0:
            raise RuntimeError("Android offscreen: general writeback branch not found")
        text = (
            text[:small_start]
            + "#if !defined(__ANDROID__) /* ANDROID_SKIP_LEGACY_SMALL_OFFSCREEN */\n"
            + text[small_start:general_else]
            + "\n#endif\n"
            + text[general_else:]
        )
        print("[applied] bypass legacy small offscreen upload on Android")
    else:
        print("[already applied] bypass legacy small offscreen upload on Android")

    marker = "ANDROID_SYNC_OFFSCREEN_PACK"
    if marker not in text:
        function_pos = text.index(function_anchor)
        general_else = text.find("\n\t\telse\n\t\t{\n#if USE_OFFSCREEN_BLIT", function_pos)
        if general_else < 0:
            raise RuntimeError("Android offscreen: general branch anchor not found after wrapping")
        block_start = text.find("#if USE_OFFSCREEN_BLIT", general_else)
        copy_call = text.find(
            "GR_CopyRGBAFramebufferToVRAM((u_int*)g_glOffscreenPBO.pixels,",
            block_start,
        )
        if block_start < 0 or copy_call < 0:
            raise RuntimeError("Android offscreen: raw blit/PBO block start or copy call not found")
        block_end = text.find("\n\t\t}", copy_call)
        if block_end < 0:
            raise RuntimeError("Android offscreen: raw blit/PBO block end not found")
        block_end += len("\n\t\t}")
        original = text[block_start:block_end]
        replacement = (
            "#if defined(__ANDROID__) /* ANDROID_SYNC_OFFSCREEN_PACK */\n"
            "\t\tGR_AndroidPackOffscreenToVram();\n"
            "#else\n"
            + original
            + "\n#endif"
        )
        text = text[:block_start] + replacement + text[block_end:]
        print("[applied] replace Android raw offscreen blit with RGB555 pack")
    else:
        print("[already applied] replace Android raw offscreen blit with RGB555 pack")

    RENDER.write_text(text, encoding="utf-8")


def patch_polygon_cull() -> None:
    text = GPU.read_text(encoding="utf-8")
    if 'extern "C" { int g_PsxPolySizeCull = 0; }' not in text:
        old = 'extern "C" { int g_PsxPolySizeCull = 1; }'
        require_once(text, old, "Android polygon-size cull")
        new = '''#if defined(__ANDROID__)
/* The mobile drawable/widescreen mapping can move valid affine world triangles
 * beyond the original PSX bbox threshold. Dropping them creates road/floor holes. */
extern "C" { int g_PsxPolySizeCull = 0; }
#else
extern "C" { int g_PsxPolySizeCull = 1; }
#endif'''
        text = text.replace(old, new, 1)
        GPU.write_text(text, encoding="utf-8")
        print("[applied] disable destructive PSX polygon-size cull on Android")
    else:
        print("[already applied] disable destructive PSX polygon-size cull on Android")


def patch_audio() -> None:
    text = AUDIO.read_text(encoding="utf-8")

    if "attrs[n++] = 48000;" not in text:
        pattern = re.compile(r"(?P<i>[ \t]*)attrs\[n\+\+\] = ALC_FREQUENCY;\n(?P=i)attrs\[n\+\+\] = 44100;")
        match = pattern.search(text)
        if not match:
            raise RuntimeError("Android audio: context frequency block not found")
        i = match.group("i")
        replacement = (
            f"{i}attrs[n++] = ALC_FREQUENCY;\n"
            "#if defined(__ANDROID__)\n"
            f"{i}attrs[n++] = 48000;\n"
            "#else\n"
            f"{i}attrs[n++] = 44100;\n"
            "#endif"
        )
        text = text[:match.start()] + replacement + text[match.end():]
        print("[applied] request Android OpenAL output at 48 kHz")
    else:
        print("[already applied] request Android OpenAL output at 48 kHz")

    if "Android: opening default OpenAL output device" not in text:
        start = text.find("\tdevStrptr = alcGetString(NULL, ALC_DEVICE_SPECIFIER);")
        end_token = "\tif(numDevices == 0)\n\t\treturn 0;"
        end = text.find(end_token, start)
        if start < 0 or end < 0:
            raise RuntimeError("Android audio: optional enumeration block not found")
        end += len(end_token)
        replacement = r'''#if defined(__ANDROID__)
	/* Enumeration is optional. Android may expose a working default device while
	 * returning no ALC_DEVICE_SPECIFIER list, so open the default directly. */
	numDevices = 1;
	eprintinfo("Android: opening default OpenAL output device\n");
#else
	devStrptr = alcGetString(NULL, ALC_DEVICE_SPECIFIER);
	devices = devStrptr;

	if (devStrptr != NULL)
	{
		while ((*devStrptr) != '\0')
		{
			eprintinfo("found sound device: %s\n", devStrptr);
			devStrptr += strlen(devStrptr) + 1;
			numDevices++;
		}
	}

	if (numDevices == 0)
		return 0;
#endif'''
        text = text[:start] + replacement + text[end:]
        print("[applied] open Android default OpenAL device without enumeration")
    else:
        print("[already applied] open Android default OpenAL device without enumeration")

    if "Android OpenAL device ready" not in text:
        open_anchor = text.find("\tg_ALCdevice = alcOpenDevice(NULL);")
        start = text.find("\tif (!g_ALCdevice)", open_anchor)
        if open_anchor < 0 or start < 0:
            raise RuntimeError("Android audio: device-open failure block not found")
        end = text.find("\n\t}", start)
        if end < 0:
            raise RuntimeError("Android audio: device-open failure block end not found")
        end += len("\n\t}")
        log = r'''
#if defined(__ANDROID__)
	{
		const char* openedName = alcGetString(g_ALCdevice, ALC_DEVICE_SPECIFIER);
		eprintinfo("Android OpenAL device ready: %s\n",
		           openedName != NULL ? openedName : "default");
	}
#endif'''
        text = text[:end] + log + text[end:]
        print("[applied] log successful Android OpenAL device")
    else:
        print("[already applied] log successful Android OpenAL device")

    AUDIO.write_text(text, encoding="utf-8")


def verify() -> None:
    render = RENDER.read_text(encoding="utf-8")
    gpu = GPU.read_text(encoding="utf-8")
    audio = AUDIO.read_text(encoding="utf-8")
    required = {
        "render": (
            "GR_RefreshAndroidDrawableSize",
            "SDL_GL_GetDrawableSize",
            "GR_AndroidPackOffscreenToVram",
            "ANDROID_SYNC_OFFSCREEN_PACK",
            "GR_DirectUploadVRAMRegion(g_PreviousOffscreen.x",
            "const u_char* rgba = (const u_char*)&c;",
            "assert(y + h <= VRAM_HEIGHT);",
        ),
        "gpu": ('extern "C" { int g_PsxPolySizeCull = 0; }',),
        "audio": (
            "Android: opening default OpenAL output device",
            "Android OpenAL device ready",
            "attrs[n++] = 48000;",
        ),
    }
    missing = [f"render:{x}" for x in required["render"] if x not in render]
    missing += [f"gpu:{x}" for x in required["gpu"] if x not in gpu]
    missing += [f"audio:{x}" for x in required["audio"] if x not in audio]
    if missing:
        raise RuntimeError(f"Android ARMv7 runtime patch verification failed: {missing}")
    print("Android ARMv7 drawable, RGB555, geometry and audio fixes verified.")


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_drawable_size()
    patch_rgb555_pack()
    patch_offscreen_writeback()
    patch_polygon_cull()
    patch_audio()
    verify()
    print("Android ARMv7 runtime fixes applied successfully.")
