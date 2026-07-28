#!/usr/bin/env python3
"""Apply focused Android ARMv7 runtime fixes after the base GLES patches.

This patch deliberately avoids rewriting the full GR_SetOffscreenState body.
Android intercepts the offscreen writeback at the start of the legacy branch,
packs the RGBA target into PSX RGB555 words, uploads that CPU VRAM region, and
returns. Desktop keeps the original path untouched.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"
GPU = PSYCROSS / "src" / "gpu" / "PsyX_GPU.cpp"
AUDIO = PSYCROSS / "src" / "audio" / "PsyX_SPUAL.cpp"


def find_required(text: str, needle: str, label: str, start: int = 0) -> int:
    pos = text.find(needle, start)
    if pos < 0:
        raise RuntimeError(f"{label}: marker not found: {needle!r}")
    return pos


def patch_drawable_size() -> None:
    text = RENDER.read_text(encoding="utf-8")
    signature = "void GR_BeginScene()"
    begin = find_required(text, signature, "Android drawable function")

    if "static void GR_RefreshAndroidDrawableSize(void)" not in text:
        helper = r'''#if defined(__ANDROID__)
/* Android system bars/cutouts can make the EGL drawable differ from the SDL
 * window request. Viewport, scissor and widescreen math must use real pixels. */
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
        text = text[:begin] + helper + text[begin:]
        begin += len(helper)
        print("[applied] add Android drawable-size helper")
    else:
        begin = text.index(signature)
        print("[already applied] add Android drawable-size helper")

    function_end = text.find("\nvoid ", begin + len(signature))
    if function_end < 0:
        function_end = len(text)
    call_marker = "GR_RefreshAndroidDrawableSize();"
    if call_marker not in text[begin:function_end]:
        opening = re.search(r"void\s+GR_BeginScene\s*\(\s*\)\s*\{", text[begin:function_end])
        if not opening:
            raise RuntimeError("Android drawable: GR_BeginScene opening brace not found")
        insert_at = begin + opening.end()
        call = "\n#if defined(__ANDROID__)\n\tGR_RefreshAndroidDrawableSize();\n#endif"
        text = text[:insert_at] + call + text[insert_at:]
        print("[applied] refresh drawable size before every frame")
    else:
        print("[already applied] refresh drawable size before every frame")

    RENDER.write_text(text, encoding="utf-8")


def patch_offscreen_writeback() -> None:
    text = RENDER.read_text(encoding="utf-8")
    signature = "void GR_SetOffscreenState(const RECT16* offscreenRect, int enable)"
    function_pos = find_required(text, signature, "Android offscreen function")

    helper_marker = "static void GR_AndroidPackOffscreenToVram(void)"
    if helper_marker not in text:
        helper = r'''#if defined(__ANDROID__)
/* The offscreen target contains ordinary RGBA pixels. PSX VRAM textures contain
 * the low/high bytes of one RGB555 word. A raw FBO blit therefore turns colours
 * into packed-word garbage (the red cutscene result). Pack explicitly instead. */
static void GR_AndroidPackOffscreenToVram(void)
{
    const int x = g_PreviousOffscreen.x;
    const int y = g_PreviousOffscreen.y;
    const int w = g_PreviousOffscreen.w;
    const int h = g_PreviousOffscreen.h;
    if (w <= 0 || h <= 0)
    {
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        return;
    }

    const size_t pixelCount = (size_t)w * (size_t)h;
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
    glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, rgbaPixels);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);

    /* glReadPixels starts at the framebuffer bottom. Store row 0 at the PSX
     * rect top, matching the legacy flip_y=1 path. */
    for (int dstRow = 0; dstRow < h; dstRow++)
    {
        const int srcRow = h - dstRow - 1;
        ushort* dst = vram + (size_t)(y + dstRow) * VRAM_WIDTH + x;
        const u_char* src = (const u_char*)&rgbaPixels[(size_t)srcRow * w];
        for (int col = 0; col < w; col++, src += 4)
        {
            const ushort r = (ushort)(src[0] >> 3);
            const ushort g = (ushort)(src[1] >> 3);
            const ushort b = (ushort)(src[2] >> 3);
            const ushort a = (ushort)((r | g | b) != 0 ? 1 : 0);
            dst[col] = (ushort)(r | (g << 5) | (b << 10) | (a << 15));
        }
    }

    GR_DirectUploadVRAMRegion(x, y, w, h);
}
#endif

'''
        text = text[:function_pos] + helper + text[function_pos:]
        function_pos += len(helper)
        print("[applied] add direct Android RGB555 offscreen packer")
    else:
        function_pos = text.index(signature)
        print("[already applied] add direct Android RGB555 offscreen packer")

    intercept_marker = "ANDROID_SYNC_OFFSCREEN_PACK"
    function_end = text.find("\n/* ============================================================================", function_pos)
    if function_end < 0:
        function_end = len(text)

    if intercept_marker not in text[function_pos:function_end]:
        # This comment is the first statement inside the `else` branch that
        # performs writeback. Inserting here avoids parsing/replacing the large
        # legacy #if/PBO block and is stable across indentation changes.
        writeback_comment = "/* (Display viewport / pillarbox is set above, before the early-out,"
        comment_pos = find_required(
            text,
            writeback_comment,
            "Android offscreen writeback entry",
            function_pos,
        )
        if comment_pos >= function_end:
            raise RuntimeError("Android offscreen writeback entry was outside GR_SetOffscreenState")
        line_start = text.rfind("\n", function_pos, comment_pos) + 1
        intercept = r'''#if defined(__ANDROID__) /* ANDROID_SYNC_OFFSCREEN_PACK */
		if (g_PsxSkipFramebufferStore)
			glBindFramebuffer(GL_FRAMEBUFFER, 0);
		else
			GR_AndroidPackOffscreenToVram();
		return;
#endif

'''
        text = text[:line_start] + intercept + text[line_start:]
        print("[applied] intercept Android offscreen writeback before legacy blit/PBO")
    else:
        print("[already applied] intercept Android offscreen writeback")

    RENDER.write_text(text, encoding="utf-8")


def patch_polygon_cull() -> None:
    text = GPU.read_text(encoding="utf-8")
    marker = 'extern "C" { int g_PsxPolySizeCull = 0; }'
    if marker in text:
        print("[already applied] disable destructive polygon-size cull on Android")
        return

    pattern = re.compile(
        r'extern\s+"C"\s*\{\s*int\s+g_PsxPolySizeCull\s*=\s*1\s*;\s*\}'
    )
    replacement = '''#if defined(__ANDROID__)
/* Large valid affine world triangles can cross the old PSX bbox threshold after
 * mobile viewport mapping. Dropping them creates the triangular road/floor holes. */
extern "C" { int g_PsxPolySizeCull = 0; }
#else
extern "C" { int g_PsxPolySizeCull = 1; }
#endif'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Android polygon-size cull declaration matches={count}")
    GPU.write_text(text, encoding="utf-8")
    print("[applied] disable destructive polygon-size cull on Android")


def patch_audio() -> None:
    text = AUDIO.read_text(encoding="utf-8")

    if "attrs[n++] = 48000;" not in text:
        freq = re.compile(
            r"(?P<i>[ \t]*)attrs\[n\+\+\]\s*=\s*ALC_FREQUENCY;\s*\n"
            r"(?P=i)attrs\[n\+\+\]\s*=\s*44100;"
        )
        match = freq.search(text)
        if not match:
            raise RuntimeError("Android audio frequency block not found")
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

    enum_marker = "Android: opening default OpenAL output device"
    if enum_marker not in text:
        start = find_required(
            text,
            "devStrptr = alcGetString(NULL, ALC_DEVICE_SPECIFIER);",
            "Android OpenAL enumeration start",
        )
        end_match = re.search(
            r"if\s*\(\s*numDevices\s*==\s*0\s*\)\s*\n\s*return\s+0\s*;",
            text[start:],
        )
        if not end_match:
            raise RuntimeError("Android OpenAL enumeration end not found")
        end = start + end_match.end()
        replacement = r'''#if defined(__ANDROID__)
	/* Device enumeration is optional on Android. OpenAL Soft may expose a valid
	 * default device while returning no ALC_DEVICE_SPECIFIER list. */
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
        open_pos = find_required(text, "g_ALCdevice = alcOpenDevice(NULL);", "Android OpenAL open call")
        failure = re.search(
            r"if\s*\(\s*!g_ALCdevice\s*\)\s*\{.*?return\s+0\s*;\s*\}",
            text[open_pos:],
            flags=re.DOTALL,
        )
        if not failure:
            raise RuntimeError("Android OpenAL failure block not found")
        insert_at = open_pos + failure.end()
        log = r'''
#if defined(__ANDROID__)
	{
		const char* openedName = alcGetString(g_ALCdevice, ALC_DEVICE_SPECIFIER);
		eprintinfo("Android OpenAL device ready: %s\n",
		           openedName != NULL ? openedName : "default");
	}
#endif'''
        text = text[:insert_at] + log + text[insert_at:]
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
            "dst[col] = (ushort)(r | (g << 5) | (b << 10) | (a << 15));",
            "GR_DirectUploadVRAMRegion(x, y, w, h);",
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
    patch_offscreen_writeback()
    patch_polygon_cull()
    patch_audio()
    verify()
    print("Android ARMv7 runtime fixes applied successfully.")
