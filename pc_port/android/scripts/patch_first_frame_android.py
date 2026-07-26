#!/usr/bin/env python3
"""Patch Android-only first-frame startup and persistent crash diagnostics.

This runs after apply_psycross_android.py, so it can extend the generated
main_pc.c startup-status helper without changing desktop builds.
"""

from pathlib import Path

PC_PORT = Path(__file__).resolve().parents[2]
REPO_ROOT = PC_PORT.parent
MAIN_PC = PC_PORT / "src" / "main_pc.c"
GAME_MAIN = REPO_ROOT / "src" / "bodyprog" / "sys" / "game_main.c"


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


def patch_main_pc() -> None:
    replace_once(
        MAIN_PC,
        """#ifdef __ANDROID__
#include <SDL_system.h>
#include <unistd.h>
#endif
""",
        """#ifdef __ANDROID__
#include <SDL_system.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#endif
""",
        "include Android crash-handler headers",
    )

    replace_once(
        MAIN_PC,
        """#ifdef __ANDROID__
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
        """#ifdef __ANDROID__
void PcPort_WriteStartupStatus(const char* status)
{
    FILE* f = fopen("android_startup_status.txt", "wb");
    if (f != NULL)
    {
        fputs(status, f);
        fputc('\\n', f);
        fclose(f);
    }
}

static void PcPort_CrashSignalHandler(int sig)
{
    int fd = open("android_startup_status.txt", O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd >= 0)
    {
        switch (sig)
        {
            case SIGSEGV: write(fd, "CRASH_SIGSEGV\\n", sizeof("CRASH_SIGSEGV\\n") - 1); break;
            case SIGABRT: write(fd, "CRASH_SIGABRT\\n", sizeof("CRASH_SIGABRT\\n") - 1); break;
            case SIGBUS:  write(fd, "CRASH_SIGBUS\\n",  sizeof("CRASH_SIGBUS\\n")  - 1); break;
            case SIGILL:  write(fd, "CRASH_SIGILL\\n",  sizeof("CRASH_SIGILL\\n")  - 1); break;
            case SIGFPE:  write(fd, "CRASH_SIGFPE\\n",  sizeof("CRASH_SIGFPE\\n")  - 1); break;
            default:      write(fd, "CRASH_SIGNAL\\n",  sizeof("CRASH_SIGNAL\\n")  - 1); break;
        }
        close(fd);
    }
    _exit(128 + sig);
}

static void PcPort_InstallCrashHandlers(void)
{
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    sigemptyset(&action.sa_mask);
    action.sa_handler = PcPort_CrashSignalHandler;
    action.sa_flags = SA_RESETHAND;
    sigaction(SIGSEGV, &action, NULL);
    sigaction(SIGABRT, &action, NULL);
    sigaction(SIGBUS,  &action, NULL);
    sigaction(SIGILL,  &action, NULL);
    sigaction(SIGFPE,  &action, NULL);
}
#else
#define PcPort_WriteStartupStatus(status) ((void)0)
#define PcPort_InstallCrashHandlers() ((void)0)
#endif
""",
        "install persistent native signal diagnostics",
    )

    replace_once(
        MAIN_PC,
        """    PcPort_PreparePlatformPaths();
    PcPort_WriteStartupStatus("FILES_READY");
""",
        """    PcPort_PreparePlatformPaths();
    PcPort_InstallCrashHandlers();
    PcPort_WriteStartupStatus("FILES_READY");
""",
        "activate native crash handlers",
    )

    replace_once(
        MAIN_PC,
        '    PcPort_WriteStartupStatus("RUNNING");\n',
        '    PcPort_WriteStartupStatus("ENTERING_MAINLOOP");\n',
        "make pre-MainLoop status precise",
    )

    replace_once(
        MAIN_PC,
        """    MainLoop();

    /* Cleanup */
""",
        """    MainLoop();
    PcPort_WriteStartupStatus("EXITED_NORMALLY");

    /* Cleanup */
""",
        "distinguish normal MainLoop exit",
    )


def patch_game_main() -> None:
    replace_once(
        GAME_MAIN,
        """extern void PsyX_EndScene(void);
extern void PsyX_UpdateInput(void);
""",
        """extern void PsyX_EndScene(void);
extern void PsyX_UpdateInput(void);
#ifdef __ANDROID__
extern void PcPort_WriteStartupStatus(const char* status);
#endif
""",
        "expose Android startup-status writer to MainLoop",
    )

    replace_once(
        GAME_MAIN,
        """    s32 interval;

    // Initialize engine.
    GsInitVcount();
    MemCard_SysInit();
    MemCard_SysInit2();
    MemCard_InitStatus();
    Joy_Init();
    VSyncCallback(&Screen_VSyncCallback);

    // NTSC-J moves these calls into the `HP_SAFE1`/`S__SAFE2` anti-modchip overlays,
    // likely to make sure those overlays wouldn't be patched out by pirates.
#if !VERSION_REGION_IS(NTSCJ)
    InitGeom();
    ItemScreen_TmdGsFCallInit();
#ifdef SH_PC_PORT
    /* Skip vibration init - requires PadInfoMode which may crash without real pad */
#else
    func_800890B8();
#endif
#endif

    SD_Init();
""",
        """    s32 interval;
#ifdef __ANDROID__
    int androidFirstFrame = 1;
#endif

    // Initialize engine.
#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_GSINIT");
#endif
    GsInitVcount();
#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_MEMCARD");
#endif
    MemCard_SysInit();
    MemCard_SysInit2();
    MemCard_InitStatus();
#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_JOY");
#endif
    Joy_Init();
    VSyncCallback(&Screen_VSyncCallback);

    // NTSC-J moves these calls into the `HP_SAFE1`/`S__SAFE2` anti-modchip overlays,
    // likely to make sure those overlays wouldn't be patched out by pirates.
#if !VERSION_REGION_IS(NTSCJ)
#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_GEOMETRY");
#endif
    InitGeom();
    ItemScreen_TmdGsFCallInit();
#ifdef SH_PC_PORT
    /* Skip vibration init - requires PadInfoMode which may crash without real pad */
#else
    func_800890B8();
#endif
#endif

#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_AUDIO");
#endif
    SD_Init();
#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_AUDIO_READY");
#endif
""",
        "trace MainLoop subsystem initialization",
    )

    replace_once(
        GAME_MAIN,
        """#ifdef SH_PC_PORT
    /* SD_Init -> SdInit -> SpuInit -> ResetCallback clears the VSync callback.
     * Re-register it after SD_Init to ensure the callback stays active. */
    VSyncCallback(&Screen_VSyncCallback);

    /* PC graphic-content warning. Runs after all subsystem inits
     * (GsInitVcount, MemCard, Joy, InitGeom, SD_Init) so it shares
     * the same boot pipeline as Konami/KCET — no perceptible delay
     * between warning and the next state. Hor+ OFF so the PsyCross
     * 2D ortho is (0, disp.w, disp.h, 0) — fb 0..640 maps to the
     * full window with no margin, and our quads at fb 0..640
     * stretch edge-to-edge. With hor+ ON the ortho would expand to
     * [-margin, disp.w+margin], leaving the quads inside the inner
     * 4:3 portion (white margin visible on the sides). Per-frame
     * gate at line 1371 reasserts the InGame-only rule once the
     * main loop starts. */
    {
        extern int g_PcHorPlusEnabled;
        extern void Pc_PlayWarningScreen(void);
        const int prevHor = g_PcHorPlusEnabled;
        g_PcHorPlusEnabled = 0;
        Pc_PlayWarningScreen();
        g_PcHorPlusEnabled = prevHor;
    }
#endif
    // Run game.
    while (true)
""",
        """#ifdef SH_PC_PORT
    /* SD_Init -> SdInit -> SpuInit -> ResetCallback clears the VSync callback.
     * Re-register it after SD_Init to ensure the callback stays active. */
    VSyncCallback(&Screen_VSyncCallback);

#ifdef __ANDROID__
    /* The custom PC warning path is the first renderer consumer and uses a
     * desktop-oriented packet-buffer path. Skip it on Android; the regular
     * Konami/KCET boot states still run and provide the first rendered frame. */
    PcPort_WriteStartupStatus("MAINLOOP_WARNING_SKIPPED");
#else
    /* PC graphic-content warning. Runs after all subsystem inits
     * (GsInitVcount, MemCard, Joy, InitGeom, SD_Init) so it shares
     * the same boot pipeline as Konami/KCET — no perceptible delay
     * between warning and the next state. Hor+ OFF so the PsyCross
     * 2D ortho is (0, disp.w, disp.h, 0) — fb 0..640 maps to the
     * full window with no margin, and our quads at fb 0..640
     * stretch edge-to-edge. With hor+ ON the ortho would expand to
     * [-margin, disp.w+margin], leaving the quads inside the inner
     * 4:3 portion (white margin visible on the sides). Per-frame
     * gate at line 1371 reasserts the InGame-only rule once the
     * main loop starts. */
    {
        extern int g_PcHorPlusEnabled;
        extern void Pc_PlayWarningScreen(void);
        const int prevHor = g_PcHorPlusEnabled;
        g_PcHorPlusEnabled = 0;
        Pc_PlayWarningScreen();
        g_PcHorPlusEnabled = prevHor;
    }
#endif
#endif
#ifdef __ANDROID__
    PcPort_WriteStartupStatus("MAINLOOP_LOOP_READY");
#endif
    // Run game.
    while (true)
""",
        "skip desktop warning renderer on Android",
    )

    replace_once(
        GAME_MAIN,
        """    while (true)
    {
        g_TickCount++;

#ifdef SH_PC_PORT
""",
        """    while (true)
    {
        g_TickCount++;
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_INPUT");
#endif

#ifdef SH_PC_PORT
""",
        "mark first frame input phase",
    )

    replace_once(
        GAME_MAIN,
        """        PsyX_UpdateInput();
        DbgOverlay_Update();
""",
        """        PsyX_UpdateInput();
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_INPUT_READY");
#endif
        DbgOverlay_Update();
""",
        "trace first input poll",
    )

    replace_once(
        GAME_MAIN,
        """        // Call update function for current GameState.
        g_GameStateUpdateFuncs[g_GameWork.gameState]();
#ifdef SH_PC_PORT
""",
        """        // Call update function for current GameState.
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_STATE_UPDATE");
#endif
        g_GameStateUpdateFuncs[g_GameWork.gameState]();
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_STATE_READY");
#endif
#ifdef SH_PC_PORT
""",
        "trace first game-state update",
    )

    replace_once(
        GAME_MAIN,
        """#endif
        GsDrawOt(&g_OrderingTable0[g_ActiveBufferIdx]);
#ifdef SH_PC_PORT
""",
        """#endif
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_DRAW_OT0");
#endif
        GsDrawOt(&g_OrderingTable0[g_ActiveBufferIdx]);
#ifdef SH_PC_PORT
""",
        "trace first world ordering-table draw",
    )

    replace_once(
        GAME_MAIN,
        """        ML_TRACE("OT2-draw");
#ifdef SH_PC_PORT
""",
        """        ML_TRACE("OT2-draw");
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_DRAW_OT2");
#endif
#ifdef SH_PC_PORT
""",
        "trace first UI ordering-table draw",
    )

    replace_once(
        GAME_MAIN,
        """        ML_TRACE("PsyX_EndScene");
        PsyX_EndScene();
        ML_TRACE("frame-done");
""",
        """        ML_TRACE("PsyX_EndScene");
#ifdef __ANDROID__
        if (androidFirstFrame)
            PcPort_WriteStartupStatus("FIRST_FRAME_PRESENT");
#endif
        PsyX_EndScene();
#ifdef __ANDROID__
        if (androidFirstFrame)
        {
            PcPort_WriteStartupStatus("FIRST_FRAME_PRESENTED");
            androidFirstFrame = 0;
        }
#endif
        ML_TRACE("frame-done");
""",
        "trace successful first presentation",
    )


if __name__ == "__main__":
    patch_main_pc()
    patch_game_main()
    print("Android first-frame startup fixes applied successfully.")
