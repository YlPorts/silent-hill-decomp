#!/usr/bin/env python3
"""Apply checked Android startup fixes before the native build.

The Android build uses pinned submodules. Exact checked replacements make the
build fail with a useful label when an upstream fragment changes, instead of
silently producing an APK with only part of the mobile fixes.
"""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
PSYCROSS = PC_PORT / "PsyCross"


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


def patch_psycross_main() -> None:
    path = PSYCROSS / "src" / "PsyX_main.cpp"

    replace_once(
        path,
        '\tprintf(pTempBuffer);\n',
        '\tprintf("%s", pTempBuffer);\n',
        "safe stdout format string",
    )
    replace_once(
        path,
        '\t\tfprintf(g_logStream, pTempBuffer);\n',
        '\t\tfprintf(g_logStream, "%s", pTempBuffer);\n',
        "safe logfile format string",
    )

    replace_once(
        path,
        """\t\tPsyX_SPUAL_Update();
\t}
""",
        """\t\tPsyX_SPUAL_Update();

#if defined(__ANDROID__)
\t\t/* Yield on mobile so the timing loop cannot monopolise a CPU core. */
\t\tSDL_Delay(1);
#endif
\t}
""",
        "yield Android timing thread",
    )

    replace_once(
        path,
        """\tg_intrThread = SDL_CreateThread(intrThreadMain, "psyX_intr", NULL);

\tif (NULL == g_intrThread)
\t{
\t\teprinterr("SDL_CreateThread failed: %s\\n", SDL_GetError());
\t\treturn 0;
\t}
\t
\tg_intrMutex = SDL_CreateMutex();
\tif (NULL == g_intrMutex)
\t{
\t\teprinterr("SDL_CreateMutex failed: %s\\n", SDL_GetError());
\t\treturn 0;
\t}
""",
        """\tg_intrMutex = SDL_CreateMutex();
\tif (NULL == g_intrMutex)
\t{
\t\teprinterr("SDL_CreateMutex failed: %s\\n", SDL_GetError());
\t\treturn 0;
\t}

\t/* The interrupt thread locks g_intrMutex immediately. Create the mutex
\t * first to avoid a startup race that can dereference NULL on Android. */
\tg_intrThread = SDL_CreateThread(intrThreadMain, "psyX_intr", NULL);

\tif (NULL == g_intrThread)
\t{
\t\teprinterr("SDL_CreateThread failed: %s\\n", SDL_GetError());
\t\tSDL_DestroyMutex(g_intrMutex);
\t\tg_intrMutex = NULL;
\t\treturn 0;
\t}
""",
        "create interrupt mutex before thread",
    )


def patch_psycross_render() -> None:
    path = PSYCROSS / "src" / "render" / "PsyX_render.cpp"

    replace_once(
        path,
        """int GR_InitialiseGLContext(char* windowName, int fullscreen)
{
\tint windowFlags = SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE;

#if defined(__ANDROID__)
""",
        """int GR_InitialiseGLContext(char* windowName, int fullscreen)
{
\tint windowFlags = SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE;

#if defined(RENDERER_OGLES)
\t/* SDL chooses the EGL configuration during SDL_CreateWindow, so request
\t * the GLES profile before the Android surface/window is created. */
\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, OGLES_VERSION);
\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0);
\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
#endif

#if defined(__ANDROID__)
""",
        "set GLES attributes before window creation",
    )

    replace_once(
        path,
        """\t\tscreenWidth = displayMode.w;
\t\twindowWidth = displayMode.w;
\t\tscreenHeight = displayMode.h;
\t\twindowHeight = displayMode.h;
""",
        """\t\tg_windowWidth = displayMode.w;
\t\tg_windowHeight = displayMode.h;
""",
        "use PsyCross Android window dimensions",
    )

    replace_once(
        path,
        """\t//SDL_GL_SetAttribute(SDL_GL_CONTEXT_EGL, 1);
\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, OGLES_VERSION);
\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0);
\tSDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);

""",
        "",
        "remove late GLES attributes",
    )

    replace_once(
        path,
        """\t\tglEnable(GL_MULTISAMPLE);
\t\tint actualSamples = 0;
""",
        """#if defined(RENDERER_OGL)
\t\tglEnable(GL_MULTISAMPLE);
#endif
\t\tint actualSamples = 0;
""",
        "guard desktop-only multisample enable",
    )

    replace_once(
        path,
        """\tglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
\tglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
\t{
\t\tfloat border[4] = { 1.0f, 1.0f, 1.0f, 1.0f };  /* outside the light frustum = fully lit */
\t\tglTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, border);
\t}
""",
        """#if defined(RENDERER_OGLES)
\tglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
\tglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
#else
\tglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER);
\tglTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER);
\t{
\t\tfloat border[4] = { 1.0f, 1.0f, 1.0f, 1.0f };  /* outside the light frustum = fully lit */
\t\tglTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, border);
\t}
#endif
""",
        "replace unsupported GLES border clamp",
    )

    replace_once(
        path,
        """\tglFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, g_shadowDepthTex, 0);
\tglDrawBuffer(GL_NONE);
\tglReadBuffer(GL_NONE);
""",
        """\tglFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, g_shadowDepthTex, 0);
#if defined(RENDERER_OGLES)
\t{
\t\tconst GLenum drawBuffers[] = { GL_NONE };
\t\tglDrawBuffers(1, drawBuffers);
\t}
#else
\tglDrawBuffer(GL_NONE);
#endif
\tglReadBuffer(GL_NONE);
""",
        "use GLES-compatible depth-only framebuffer setup",
    )


def patch_host_startup() -> None:
    path = PC_PORT / "src" / "main_pc.c"

    replace_once(
        path,
        """#ifdef _WIN32
#define SH_NULL_DEVICE "NUL"
#else
#define SH_NULL_DEVICE "/dev/null"
#endif
""",
        """#ifdef _WIN32
#define SH_NULL_DEVICE "NUL"
#else
#define SH_NULL_DEVICE "/dev/null"
#endif

#ifdef __ANDROID__
static void PcPort_WriteStartupStatus(const char* status)
{
    FILE* f = fopen("android_startup_status.txt", "wb");
    if (f != NULL)
    {
        fputs(status, f);
        fputc('\\n', f);
        fclose(f);
    }
}
#else
#define PcPort_WriteStartupStatus(status) ((void)0)
#endif
""",
        "add Android startup status writer",
    )

    replace_once(
        path,
        """    PcPort_PreparePlatformPaths();

    PrintBanner();
""",
        """    PcPort_PreparePlatformPaths();
    PcPort_WriteStartupStatus("FILES_READY");

    PrintBanner();
""",
        "mark private files ready",
    )

    replace_once(
        path,
        """    /* Initialize PsyCross (creates SDL2 window + OpenGL context) */
    SH_LOG("Initializing PsyCross (SDL2 + OpenGL)...");
    PsyX_Initialise("Silent Hill", windowWidth, windowHeight, g_PcConfig.fullscreen);

    SH_LOG("PsyCross initialized. Window: %dx%d", windowWidth, windowHeight);
""",
        """    /* Initialize PsyCross (creates SDL2 window + OpenGL context) */
    PcPort_WriteStartupStatus("STARTING_GRAPHICS");
    SH_LOG("Initializing PsyCross (SDL2 + OpenGL)...");
    PsyX_Initialise("Silent Hill", windowWidth, windowHeight, g_PcConfig.fullscreen);

    {
        extern SDL_Window* g_window;
        const char* gl_version = (const char*)glGetString(GL_VERSION);
        if (g_window == NULL || gl_version == NULL)
        {
            PcPort_WriteStartupStatus("ERROR_GRAPHICS_CONTEXT");
            SH_LOG("Android startup failed: SDL/OpenGL ES context was not created");
            return 2;
        }
    }
    PcPort_WriteStartupStatus("GRAPHICS_READY");
    SH_LOG("PsyCross initialized. Window: %dx%d", windowWidth, windowHeight);
""",
        "validate Android graphics startup",
    )

    replace_once(
        path,
        """        if (cdImagePath[0]) {
            SH_LOG("CD image found, initializing CDFS...");
            PsyX_CDFS_Init(cdImagePath, 0, 0);
""",
        """        if (cdImagePath[0]) {
            PcPort_WriteStartupStatus("STARTING_DISC");
            SH_LOG("CD image found, initializing CDFS...");
            PsyX_CDFS_Init(cdImagePath, 0, 0);
            PcPort_WriteStartupStatus("DISC_READY");
""",
        "mark disc initialization",
    )

    replace_once(
        path,
        """    SH_LOG("All subsystems initialized. Entering MainLoop...");

    /* The graphic-content warning""",
        """    SH_LOG("All subsystems initialized. Entering MainLoop...");
    PcPort_WriteStartupStatus("RUNNING");

    /* The graphic-content warning""",
        "mark main loop running",
    )


if __name__ == "__main__":
    if not PSYCROSS.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {PSYCROSS}")
    patch_psycross_main()
    patch_psycross_render()
    patch_host_startup()
    print("Android native startup fixes applied successfully.")
