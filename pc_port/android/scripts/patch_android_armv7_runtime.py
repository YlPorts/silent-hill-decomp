#!/usr/bin/env python3
"""Apply focused Android ARMv7 runtime fixes after the base GLES patches.

This patch deliberately leaves the ordering-table walker and vertex layout alone.
It fixes four Android-specific runtime problems observed on-device:
  * use SDL's real GL drawable dimensions for viewport/projection math;
  * stop the PSX polygon-size compatibility rule from deleting valid mobile polys;
  * pack offscreen RGBA scenes back into RGB555 before writing VRAM;
  * open OpenAL's default Android device even when enumeration is unavailable.
"""

from pathlib import Path
import re

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"
RENDER = PSYCROSS / "src" / "render" / "PsyX_render.cpp"
GPU = PSYCROSS / "src" / "gpu" / "PsyX_GPU.cpp"
AUDIO = PSYCROSS / "src" / "audio" / "PsyX_SPUAL.cpp"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"[already applied] {label}")
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[applied] {label}")


def patch_drawable_size() -> None:
    text = RENDER.read_text(encoding="utf-8")
    helper_marker = "GR_RefreshAndroidDrawableSize"
    if helper_marker not in text:
        anchor = "void GR_BeginScene()\n"
        pos = text.find(anchor)
        if pos < 0:
            raise RuntimeError("Android drawable size: GR_BeginScene was not found")
        helper = r'''#if defined(__ANDROID__)
/* SDL's display mode can include pixels that are not part of the actual EGL
 * surface (status/navigation insets). glViewport and the widescreen projection
 * must use the drawable size, not the requested window/display mode. */
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
        print("[applied] add Android drawable-size refresh helper")
    else:
        print("[already applied] add Android drawable-size refresh helper")

    old = "void GR_BeginScene()\n{\n\tg_lastBoundTexture = 0;\n"
    new = "void GR_BeginScene()\n{\n#if defined(__ANDROID__)\n\tGR_RefreshAndroidDrawableSize();\n#endif\n\tg_lastBoundTexture = 0;\n"
    if new not in text:
        if text.count(old) != 1:
            raise RuntimeError("Android drawable size: GR_BeginScene entry did not match")
        text = text.replace(old, new, 1)
        print("[applied] refresh drawable size before every frame")
    else:
        print("[already applied] refresh drawable size before every frame")

    RENDER.write_text(text, encoding="utf-8")


def patch_rgb555_pack() -> None:
    old = '''\t\t\tu_char b = ((c >> 3) & 0x1F);
\t\t\tu_char g = ((c >> 11) & 0x1F);
\t\t\tu_char r = ((c >> 19) & 0x1F);
\t\t\t//u_char a = ((c >> 24) & 0x1F);

\t\t\tint a = r == g == b == 0 ? 0 : 1;

\t\t\t*data_dst++ = r | (g << 5) | (b << 10) | (a << 15);
'''
    new = '''\t\t\t/* glReadPixels(GL_RGBA/UNSIGNED_BYTE) is R,G,B,A byte order.
\t\t\t * The old code read the little-endian word backwards (R<->B) and
\t\t\t * used a chained equality expression that is not valid as an all-zero
\t\t\t * test. Pack the exact PSX RGB555 word explicitly. */
\t\t\tconst u_char* rgba = (const u_char*)&c;
\t\t\tu_char r = (u_char)(rgba[0] >> 3);
\t\t\tu_char g = (u_char)(rgba[1] >> 3);
\t\t\tu_char b = (u_char)(rgba[2] >> 3);
\t\t\tint a = (r | g | b) != 0 ? 1 : 0;

\t\t\t*data_dst++ = (ushort)(r | (g << 5) | (b << 10) | (a << 15));
'''
    replace_once(RENDER, old, new, "pack framebuffer RGBA into correct PSX RGB555")

    replace_once(
        RENDER,
        "\tassert(y + h <= VRAM_WIDTH);\n",
        "\tassert(y + h <= VRAM_HEIGHT);\n",
        "validate framebuffer copy against VRAM height",
    )


def patch_offscreen_writeback() -> None:
    text = RENDER.read_text(encoding="utf-8")

    # The <=64 scratch path uploads 16-bit words with VRAM_FORMAT. After the
    # Android RGBA8 transport patch VRAM_FORMAT is GL_RGBA, so that path would
    # read four bytes per pixel from a two-byte array. Route all Android sizes
    # through the single correct pack/upload path below.
    small_start = '''\t\telse if (g_PreviousOffscreen.w > 0 && g_PreviousOffscreen.h > 0 &&
\t\t         g_PreviousOffscreen.w <= 64 && g_PreviousOffscreen.h <= 64)
'''
    if "ANDROID_SKIP_LEGACY_SMALL_OFFSCREEN" not in text:
        idx = text.find(small_start)
        if idx < 0:
            raise RuntimeError("Android offscreen: legacy small-scratch branch not found")
        next_else = text.find("\n\t\telse\n\t\t{\n#if USE_OFFSCREEN_BLIT", idx)
        if next_else < 0:
            raise RuntimeError("Android offscreen: general writeback branch not found")
        text = (
            text[:idx]
            + "#if !defined(__ANDROID__) /* ANDROID_SKIP_LEGACY_SMALL_OFFSCREEN */\n"
            + text[idx:next_else]
            + "\n#endif\n"
            + text[next_else:]
        )
        print("[applied] bypass legacy small offscreen upload on Android RGBA8")
    else:
        print("[already applied] bypass legacy small offscreen upload on Android RGBA8")

    marker = "ANDROID_SYNC_OFFSCREEN_PACK"
    if marker not in text:
        start = text.find("#if USE_OFFSCREEN_BLIT", text.find("void GR_SetOffscreenState"))
        if start < 0:
            raise RuntimeError("Android offscreen: raw blit start not found")
        pattern = re.compile(
            r"#if USE_OFFSCREEN_BLIT\n.*?"
            r"GR_CopyRGBAFramebufferToVRAM\(\(u_int\*\)g_glOffscreenPBO\.pixels,\n"
            r"\s*g_PreviousOffscreen\.x, g_PreviousOffscreen\.y, g_PreviousOffscreen\.w, g_PreviousOffscreen\.h,\n"
            r"\s*USE_OFFSCREEN_BLIT == 0, 1\);\n"
            r"\s*\}",
            re.DOTALL,
        )
        match = pattern.search(text, start)
        if not match:
            raise RuntimeError("Android offscreen: raw blit/PBO block not found")
        original = match.group(0)
        android = r'''#if defined(__ANDROID__) /* ANDROID_SYNC_OFFSCREEN_PACK */
        /* The offscreen FBO contains normal RGBA pixels, while the VRAM texture
         * stores each PSX pixel as the bytes of one RGB555 word. A raw blit
         * copies colours as bytes and destroys later texture/CLUT decoding.
         * Read this small PSX-sized target synchronously, pack RGB555 into the
         * authoritative CPU VRAM, then use the existing Android RGBA expansion
         * to update both VRAM textures immediately. */
        {
            const int aw = g_PreviousOffscreen.w;
            const int ah = g_PreviousOffscreen.h;
            const size_t pixelCount = (size_t)aw * (size_t)ah;
            static u_int* s_androidOffscreenRGBA = NULL;
            static size_t s_androidOffscreenCapacity = 0;

            if (pixelCount > s_androidOffscreenCapacity)
            {
                u_int* resized = (u_int*)realloc(s_androidOffscreenRGBA,
                                                 pixelCount * sizeof(u_int));
                if (resized != NULL)
                {
                    s_androidOffscreenRGBA = resized;
                    s_androidOffscreenCapacity = pixelCount;
                }
            }

            if (s_androidOffscreenRGBA != NULL &&
                s_androidOffscreenCapacity >= pixelCount)
            {
                glBindFramebuffer(GL_FRAMEBUFFER, g_glOffscreenFramebuffer);
                glReadPixels(0, 0, aw, ah, GL_RGBA, GL_UNSIGNED_BYTE,
                             s_androidOffscreenRGBA);
                glBindFramebuffer(GL_FRAMEBUFFER, 0);

                GR_CopyRGBAFramebufferToVRAM(s_androidOffscreenRGBA,
                    g_PreviousOffscreen.x, g_PreviousOffscreen.y, aw, ah, 0, 1);
                GR_DirectUploadVRAMRegion(g_PreviousOffscreen.x,
                    g_PreviousOffscreen.y, aw, ah);
            }
            else
            {
                glBindFramebuffer(GL_FRAMEBUFFER, 0);
                eprintwarn("Android offscreen RGB555 buffer allocation failed\n");
            }
        }
#else
''' + original + r'''
#endif'''
        text = text[:match.start()] + android + text[match.end():]
        print("[applied] replace Android raw offscreen blit with RGB555 pack")
    else:
        print("[already applied] replace Android raw offscreen blit with RGB555 pack")

    RENDER.write_text(text, encoding="utf-8")


def patch_polygon_cull() -> None:
    old = 'extern "C" { int g_PsxPolySizeCull = 1; }\n'
    new = '''#if defined(__ANDROID__)
/* Mobile Hor+/drawable differences can push otherwise valid affine world
 * triangles beyond the PSX hardware bounding-box threshold. Dropping them
 * creates the large triangular holes seen in roads and floors. */
extern "C" { int g_PsxPolySizeCull = 0; }
#else
extern "C" { int g_PsxPolySizeCull = 1; }
#endif
'''
    replace_once(GPU, old, new, "disable destructive PSX polygon-size cull on Android")


def patch_audio() -> None:
    text = AUDIO.read_text(encoding="utf-8")

    old_freq = '''\tattrs[n++] = ALC_FREQUENCY;
\tattrs[n++] = 44100;
'''
    new_freq = '''\tattrs[n++] = ALC_FREQUENCY;
#if defined(__ANDROID__)
\t/* Android's native output path is normally 48 kHz. Avoid forcing OpenAL
\t * through a 44.1 kHz device conversion path on mobile. */
\tattrs[n++] = 48000;
#else
\tattrs[n++] = 44100;
#endif
'''
    if new_freq not in text:
        if text.count(old_freq) != 1:
            raise RuntimeError("Android audio: context frequency block not found")
        text = text.replace(old_freq, new_freq, 1)
        print("[applied] request Android OpenAL output at 48 kHz")
    else:
        print("[already applied] request Android OpenAL output at 48 kHz")

    marker = "Android: opening default OpenAL output device"
    if marker not in text:
        pattern = re.compile(
            r"\tdevStrptr = alcGetString\(NULL, ALC_DEVICE_SPECIFIER\);\n"
            r"\tdevices = devStrptr;\n\n"
            r"\t// go through device list.*?"
            r"\tif\(numDevices == 0\)\n"
            r"\t\treturn 0;\n",
            re.DOTALL,
        )
        replacement = r'''#if defined(__ANDROID__)
	/* Device enumeration is optional in OpenAL. Some Android backends expose a
	 * perfectly usable default output but return no ALC_DEVICE_SPECIFIER list;
	 * the old early return therefore disabled all sound before alcOpenDevice.
	 * Open the default device directly on Android. */
	numDevices = 1;
	eprintinfo("Android: opening default OpenAL output device\n");
#else
	devStrptr = alcGetString(NULL, ALC_DEVICE_SPECIFIER);
	devices = devStrptr;

	if (devStrptr != NULL)
	{
		// go through device list (each device terminated with a single NULL, list terminated with double NULL)
		while ((*devStrptr) != '\0')
		{
			eprintinfo("found sound device: %s\n", devStrptr);
			devStrptr += strlen(devStrptr) + 1;
			numDevices++;
		}
	}

	if (numDevices == 0)
		return 0;
#endif
'''
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"Android audio: optional enumeration block matches={count}")
        print("[applied] open Android default OpenAL device without enumeration")
    else:
        print("[already applied] open Android default OpenAL device without enumeration")

    open_success = '''\tif (!g_ALCdevice)
\t{
\t\talErr = alcGetError(NULL);
\t\teprinterr("alcOpenDevice: NULL DEVICE error: %s\\n", getALCErrorString(alErr));
\t\treturn 0;
\t}
'''
    open_logged = open_success + '''#if defined(__ANDROID__)
\t{
\t\tconst char* openedName = alcGetString(g_ALCdevice, ALC_DEVICE_SPECIFIER);
\t\teprintinfo("Android OpenAL device ready: %s\\n",
\t\t           openedName != NULL ? openedName : "default");
\t}
#endif
'''
    if "Android OpenAL device ready" not in text:
        if text.count(open_success) != 1:
            raise RuntimeError("Android audio: device-open result block not found")
        text = text.replace(open_success, open_logged, 1)
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
            "ANDROID_SYNC_OFFSCREEN_PACK",
            "GR_DirectUploadVRAMRegion(g_PreviousOffscreen.x",
            "const u_char* rgba = (const u_char*)&c;",
            "assert(y + h <= VRAM_HEIGHT);",
        ),
        "gpu": ("extern \"C\" { int g_PsxPolySizeCull = 0; }",),
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
