#!/usr/bin/env python3
"""Apply Android-specific PsyCross fixes with checked source replacements.

A checked replacement is more robust than a hand-maintained unified diff for the
pinned submodule: every expected source fragment must occur exactly once, or the
build stops with a useful error naming the missing transformation.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "PsyCross"


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


def patch_main() -> None:
    path = ROOT / "src" / "PsyX_main.cpp"

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


def patch_render() -> None:
    path = ROOT / "src" / "render" / "PsyX_render.cpp"

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


if __name__ == "__main__":
    if not ROOT.is_dir():
        raise SystemExit(f"PsyCross submodule not found at {ROOT}")
    patch_main()
    patch_render()
    print("Android PsyCross compatibility fixes applied successfully.")
