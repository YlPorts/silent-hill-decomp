/*
 * main_pc.c - Silent Hill PC Port entry point
 *
 * This replaces the PSX main() with a PC-compatible version that:
 * 1. Initializes SDL2 + OpenGL via PsyCross
 * 2. Sets up the file system to read game data from disk
 * 3. Calls into the original game code
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <time.h>

#ifndef __ANDROID__
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#ifdef __ANDROID__
#include <SDL_system.h>
#include <unistd.h>
#endif

#include "common.h"
#include "game.h"
#include "gpu.h"
#include "sh_log.h"
#include "psx_memory.h"
#include "pc_config.h"
#include "map_registry.h"
#include "main/fsqueue.h"
#include "main/fileinfo.h"
#include "bodyprog/bodyprog.h"
#include "maps/shared/SysWork_StateStepIncrementAfterTime.h"

#include <libgpu.h>
#include <libgte.h>
#include <libetc.h>
#include <libspu.h>
#include <libcd.h>

/* PsyCross public API */
#include <PsyX/PsyX_public.h>
#ifdef __ANDROID__
#include <GLES3/gl3.h>
#else
#include <PsyX/common/glad.h>
#endif

/* Null device differs by platform: NUL on Windows, /dev/null on POSIX. */
#ifdef _WIN32
#define SH_NULL_DEVICE "NUL"
#else
#define SH_NULL_DEVICE "/dev/null"
#endif

/* Forward declarations from game code */
extern void MainLoop(void);
extern void Fs_QueueInitialize(void);
extern void PcPort_InitCharaAnimInfo(void);

/* Overlay pointers from main.c - need runtime init on PC */
extern void* g_OvlDynamic;
extern void* g_OvlBodyprog;

/* PC port: master gate for dev/cheat keys (config: allow_debug_controls).
 * Read by DebugCamera_Update + the few stragglers. Off by default. */
int g_PcAllowDebugControls = 0;

/* PC port: unlimited-enemies mode (config: unlimited_enemies, console: unlimited).
 * When on, the per-room concurrent-NPC cap is raised to NPC_COUNT_MAX so natural
 * spawns can fill every slot. Read in npc_main.c. Off by default. */
int g_PcUnlimitedEnemies = 0;

/* "Mouse1".."Mouse5" -> SDL mouse button number (Mouse1=left, Mouse2=right,
 * Mouse3=middle, Mouse4=X1, Mouse5=X2). "MouseWheelUp"/"MouseWheelDown" -> the
 * two pseudo-slots 6/7 consumed by PsyX_Pad_BuildMouseWord (the wheel is
 * event-based, latched there). Returns 0 if not a mouse name. */
static int Pc_ParseMouseName(const char* v)
{
    if (!v) return 0;
    if (SDL_strcasecmp(v, "MouseWheelUp")   == 0) return 6;
    if (SDL_strcasecmp(v, "MouseWheelDown") == 0) return 7;
    if ((v[0] == 'M' || v[0] == 'm') && (v[1] == 'o' || v[1] == 'O') &&
        (v[2] == 'u' || v[2] == 'U') && (v[3] == 's' || v[3] == 'S') &&
        (v[4] == 'e' || v[4] == 'E'))
    {
        switch (atoi(v + 5))
        {
            case 1: return SDL_BUTTON_LEFT;
            case 2: return SDL_BUTTON_RIGHT;
            case 3: return SDL_BUTTON_MIDDLE;
            case 4: return SDL_BUTTON_X1;
            case 5: return SDL_BUTTON_X2;
        }
    }
    return 0;
}

/* Apply a "key or mouse" bind value to a PSX-button slot: an SDL key name goes
 * into *kc (scancode); a "MouseN" value adds the PSX bit to the mouse mask and
 * leaves *kc unbound; "NONE"/empty = unbound. Used for BOTH the primary and the
 * secondary keyboard binds so the mouse can be a PRIMARY bind (e.g. modern
 * Fire = Left Mouse). The caller clears the mouse mask once before applying. */
static void Pc_ApplyKeyOrMouse(const char* v, unsigned short bit, int* kc)
{
    int mb;
    if (!v || !v[0] || strcmp(v, "NONE") == 0) { *kc = SDL_SCANCODE_UNKNOWN; return; }
    mb = Pc_ParseMouseName(v);
    if (mb > 0) { g_cfg_mouseButtonMask[mb] |= bit; *kc = SDL_SCANCODE_UNKNOWN; }
    else        { *kc = PsyX_LookupKeyboardMapping(v, SDL_SCANCODE_UNKNOWN); }
}

/* Apply ONE control scheme (classic or altcam) onto the PsyCross input mapping.
 * Rebuilds all four mappings from scratch each call (primary keyboard, secondary
 * keyboard, primary controller, secondary controller) + the mouse mask, so a
 * runtime scheme swap is just "re-run with the other scheme". Unbound = "NONE"
 * -> SDL_SCANCODE_UNKNOWN / BUTTON_INVALID; nothing falls back to a built-in
 * default, so the config is fully respected. Call via Pc_ApplyActiveControlScheme. */
static void Pc_ApplyControlConfig(const ControlScheme* s)
{
    extern int g_cfg_controllerMovement;
    int i;

    /* Reset the keyboard layers' mouse contribution; rebuilt from primary + secondary. */
    for (i = 0; i < 8; i++) g_cfg_mouseButtonMask[i] = 0;

    /* Primary keyboard (key OR mouse button). */
    Pc_ApplyKeyOrMouse(s->keyUp,       0x10,   &g_cfg_keyboardMapping.kc_dpad_up);
    Pc_ApplyKeyOrMouse(s->keyDown,     0x40,   &g_cfg_keyboardMapping.kc_dpad_down);
    Pc_ApplyKeyOrMouse(s->keyLeft,     0x80,   &g_cfg_keyboardMapping.kc_dpad_left);
    Pc_ApplyKeyOrMouse(s->keyRight,    0x20,   &g_cfg_keyboardMapping.kc_dpad_right);
    Pc_ApplyKeyOrMouse(s->keyCross,    0x4000, &g_cfg_keyboardMapping.kc_cross);
    Pc_ApplyKeyOrMouse(s->keyCircle,   0x2000, &g_cfg_keyboardMapping.kc_circle);
    Pc_ApplyKeyOrMouse(s->keyTriangle, 0x1000, &g_cfg_keyboardMapping.kc_triangle);
    Pc_ApplyKeyOrMouse(s->keySquare,   0x8000, &g_cfg_keyboardMapping.kc_square);
    Pc_ApplyKeyOrMouse(s->keyL1,       0x400,  &g_cfg_keyboardMapping.kc_l1);
    Pc_ApplyKeyOrMouse(s->keyR1,       0x800,  &g_cfg_keyboardMapping.kc_r1);
    Pc_ApplyKeyOrMouse(s->keyL2,       0x100,  &g_cfg_keyboardMapping.kc_l2);
    Pc_ApplyKeyOrMouse(s->keyR2,       0x200,  &g_cfg_keyboardMapping.kc_r2);
    Pc_ApplyKeyOrMouse(s->keyL3,       0x2,    &g_cfg_keyboardMapping.kc_l3);
    Pc_ApplyKeyOrMouse(s->keyR3,       0x4,    &g_cfg_keyboardMapping.kc_r3);
    Pc_ApplyKeyOrMouse(s->keyStart,    0x8,    &g_cfg_keyboardMapping.kc_start);
    Pc_ApplyKeyOrMouse(s->keySelect,   0x1,    &g_cfg_keyboardMapping.kc_select);

    /* Secondary keyboard (second key/mouse per action; AND-combined per frame). */
    Pc_ApplyKeyOrMouse(s->keyUp2,       0x10,   &g_cfg_keyboardMapping2.kc_dpad_up);
    Pc_ApplyKeyOrMouse(s->keyDown2,     0x40,   &g_cfg_keyboardMapping2.kc_dpad_down);
    Pc_ApplyKeyOrMouse(s->keyLeft2,     0x80,   &g_cfg_keyboardMapping2.kc_dpad_left);
    Pc_ApplyKeyOrMouse(s->keyRight2,    0x20,   &g_cfg_keyboardMapping2.kc_dpad_right);
    Pc_ApplyKeyOrMouse(s->keyCross2,    0x4000, &g_cfg_keyboardMapping2.kc_cross);
    Pc_ApplyKeyOrMouse(s->keyCircle2,   0x2000, &g_cfg_keyboardMapping2.kc_circle);
    Pc_ApplyKeyOrMouse(s->keyTriangle2, 0x1000, &g_cfg_keyboardMapping2.kc_triangle);
    Pc_ApplyKeyOrMouse(s->keySquare2,   0x8000, &g_cfg_keyboardMapping2.kc_square);
    Pc_ApplyKeyOrMouse(s->keyL12,       0x400,  &g_cfg_keyboardMapping2.kc_l1);
    Pc_ApplyKeyOrMouse(s->keyR12,       0x800,  &g_cfg_keyboardMapping2.kc_r1);
    Pc_ApplyKeyOrMouse(s->keyL22,       0x100,  &g_cfg_keyboardMapping2.kc_l2);
    Pc_ApplyKeyOrMouse(s->keyR22,       0x200,  &g_cfg_keyboardMapping2.kc_r2);
    Pc_ApplyKeyOrMouse(s->keyL32,       0x2,    &g_cfg_keyboardMapping2.kc_l3);
    Pc_ApplyKeyOrMouse(s->keyR32,       0x4,    &g_cfg_keyboardMapping2.kc_r3);
    Pc_ApplyKeyOrMouse(s->keyStart2,    0x8,    &g_cfg_keyboardMapping2.kc_start);
    Pc_ApplyKeyOrMouse(s->keySelect2,   0x1,    &g_cfg_keyboardMapping2.kc_select);

    /* Primary controller. */
    g_cfg_controllerMapping.gc_cross    = PsyX_LookupGameControllerMapping(s->padCross,    SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_circle   = PsyX_LookupGameControllerMapping(s->padCircle,   SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_triangle = PsyX_LookupGameControllerMapping(s->padTriangle, SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_square   = PsyX_LookupGameControllerMapping(s->padSquare,   SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_l1       = PsyX_LookupGameControllerMapping(s->padL1,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_r1       = PsyX_LookupGameControllerMapping(s->padR1,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_l2       = PsyX_LookupGameControllerMapping(s->padL2,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_r2       = PsyX_LookupGameControllerMapping(s->padR2,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_l3       = PsyX_LookupGameControllerMapping(s->padL3,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_r3       = PsyX_LookupGameControllerMapping(s->padR3,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_start    = PsyX_LookupGameControllerMapping(s->padStart,    SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping.gc_select   = PsyX_LookupGameControllerMapping(s->padSelect,   SDL_CONTROLLER_BUTTON_INVALID);

    /* Secondary controller (second button per action; AND-combined per frame).
     * dpad/axes of mapping2 stay BUTTON_INVALID (set once in PsyX init). */
    g_cfg_controllerMapping2.gc_cross    = PsyX_LookupGameControllerMapping(s->padCross2,    SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_circle   = PsyX_LookupGameControllerMapping(s->padCircle2,   SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_triangle = PsyX_LookupGameControllerMapping(s->padTriangle2, SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_square   = PsyX_LookupGameControllerMapping(s->padSquare2,   SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_l1       = PsyX_LookupGameControllerMapping(s->padL12,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_r1       = PsyX_LookupGameControllerMapping(s->padR12,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_l2       = PsyX_LookupGameControllerMapping(s->padL22,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_r2       = PsyX_LookupGameControllerMapping(s->padR22,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_l3       = PsyX_LookupGameControllerMapping(s->padL32,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_r3       = PsyX_LookupGameControllerMapping(s->padR32,       SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_start    = PsyX_LookupGameControllerMapping(s->padStart2,    SDL_CONTROLLER_BUTTON_INVALID);
    g_cfg_controllerMapping2.gc_select   = PsyX_LookupGameControllerMapping(s->padSelect2,   SDL_CONTROLLER_BUTTON_INVALID);

    g_PcAllowDebugControls   = g_PcConfig.allowDebugControls;
    g_PcUnlimitedEnemies     = g_PcConfig.unlimitedEnemies;
    g_cfg_controllerMovement = g_PcConfig.controllerMovement;
    g_cfg_allowMouseSecondary = 1; /* mouse + secondary binds always active */
}

/* Select + apply the control scheme matching the active camera mode: altcam for
 * any alternate/modern camera (g_DebugThirdPersonCam != 0), classic otherwise.
 * Called at boot and whenever the control style (camera) changes. */
void Pc_ApplyActiveControlScheme(void)
{
    extern int g_DebugThirdPersonCam;
    Pc_ApplyControlConfig(g_DebugThirdPersonCam ? &g_PcConfig.altcam : &g_PcConfig.classic);
}

/* Force the classic (default) control scheme regardless of the active camera.
 * Menus always navigate with the default binds, so an alternate camera's binds
 * (mouse-look / remapped buttons) don't leak into menu navigation. Restored to
 * the camera-matched scheme via Pc_ApplyActiveControlScheme on return to
 * gameplay (driven by Pc_ControlStyleUpdate). */
void Pc_ApplyClassicControlScheme(void)
{
    Pc_ApplyControlConfig(&g_PcConfig.classic);
}

/* Demo play file buffer pointer - default PSX address needs runtime init */
typedef struct s_DemoFrameData s_DemoFrameData;
extern s_DemoFrameData* g_Demo_PlayFileBufferPtr;

/* Unified debug log â€” writes to a fopen'd SilentHill.log handle that
 * doesn't depend on stdout being redirected.  Lets us keep SH_DBG going
 * to the file even when show_console=1 leaves stdout pointed at the
 * visible console window.  Set g_ShDebugEchoStdout from main() after
 * config is parsed. */
FILE* g_ShDebugLog = NULL;
int   g_ShDebugEchoStdout = 0;
void (*g_ShOverlayPushLine)(const char* line) = NULL;
void (*g_ShOverlayToastLine)(const char* line) = NULL;
/* Per-run timestamped log path so a new run never overwrites the previous log.
 * Computed once on the first call and cached, so the main log handle and the
 * stdout/stderr freopen all target the same file for this run. */
const char* SH_LogPath(void)
{
    static char s_logPath[64] = {0};
    if (!s_logPath[0]) {
        time_t now = time(NULL);
        struct tm* lt = localtime(&now);
        if (!lt || strftime(s_logPath, sizeof(s_logPath), "SilentHill_%Y%m%d_%H%M%S.log", lt) == 0) {
            snprintf(s_logPath, sizeof(s_logPath), "SilentHill.log");
        }
    }
    return s_logPath;
}

void SH_DebugLogInit(void)
{
    if (!g_ShDebugLog) {
        g_ShDebugLog = fopen(SH_LogPath(), "w");
        if (!g_ShDebugLog) {
            /* Last resort â€” fall back to stdout so we don't crash on the
             * first SH_DBG. Caller (main) normally pre-opens this. */
            g_ShDebugLog = stdout;
        } else {
            /* Full buffering (64KB). MSVCRT ignores _IOLBF (treats it as
             * _IOFBF), so request _IOFBF explicitly â€” flushes on buffer-full
             * and on clean exit. Unbuffered (_IONBF) was used for crash
             * diagnosis but it flushes every SH_DBG to disk, which halves
             * framerate under heavy per-frame logging (combat + map churn). */
            static char s_logBuf[64 * 1024];
            setvbuf(g_ShDebugLog, s_logBuf, _IOFBF, sizeof(s_logBuf));
        }
    }
}

/* Final-flush hook: ensure the log is flushed before the process exits
 * (normal or crash). Stdio also runs this via atexit but registering
 * explicitly makes the intent obvious. */
static void Sh_LogAtExitFlush(void) {
    if (g_ShDebugLog && g_ShDebugLog != stdout) fflush(g_ShDebugLog);
}

/* Bounded tail loss for crash reports. The 64KB buffer only self-flushes when
 * full, so a quiet stretch (exploration, menus) can hold minutes of log that a
 * crash then discards â€” and a crash that bypasses our SetUnhandledExceptionFilter
 * (heap corruption fast-fails straight to the kernel) never gets the handler's
 * flush either. One flush per wall-clock second caps the loss without
 * reintroducing the per-SH_DBG flush that halved framerate. */
void Sh_LogPeriodicFlush(void)
{
    static time_t s_lastFlush = 0;
    time_t now;

    if (!g_ShDebugLog || g_ShDebugLog == stdout) return;

    now = time(NULL);
    if (now == s_lastFlush) return;
    s_lastFlush = now;
    fflush(g_ShDebugLog);
}

/* Crash telemetry lives in pc_crash.c (windows.h conflicts with the decomp
 * `byte` typedef, so it can't be included here). */
extern void Sh_InstallCrashFilter(void);


/* Game data path - where the extracted game files are located */
static char g_GameDataPath[512] = "./gamedata";

/* Android applications cannot rely on the process working directory and do
 * not have unrestricted access to shared storage. The Java ïÞ¼¶‰žËkºwµçl(€€€•áÑ•É¸Ù½¥MÁ±¥Ñ!•…‘¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€MÁ±¥Ñ!•…‘¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥I½µÁ•É¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€I½µÁ•É¹¥µ%¹™½Í}%¹¥Ð ¤ì((€€€€¼¨	¥¹…Éäµ•áÑÉ…Ñ•‰…Ñ € ÈÀÈØ´ÀØ´ÄÀ¤è‰½ÍÍ•Ì€¬±…Ñ”µ…µ”…ÍÐÑ¡…ÐÝ•É”(€€€€€¨ÍÑ¥±°é•É¼µÍÑÕ‰Ì¸•¹•É…Ñ•‰äÁ}Á½ÉÐ½Ñ½½±Ì½•áÑÉ…Ñ}…¹¥µ}¥¹™½Ì¹Áä¸€¨¼(€€€•áÑ•É¸Ù½¥1½­•É•…‘	½‘å¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€1½­•É•…‘	½‘å¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥QÝ¥¹™••±•É¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€QÝ¥¹™••±•É¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥±½…ÑÍÑ¥¹•É¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€±½…ÑÍÑ¥¹•É¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥5½¹ÍÑ•Éå‰¥±¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€5½¹ÍÑ•Éå‰¥±¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥±…ÕÉ½Í¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€±…ÕÉ½Í¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥A…É…Í¥Ñ•¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€A…É…Í¥Ñ•¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥¡½ÍÑ½Ñ½É¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€¡½ÍÑ½Ñ½É¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥	±½½‘å%¹Õ‰…Ñ½É¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€	±½½‘å%¹Õ‰…Ñ½É¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥%¹Õ‰…Ñ½É¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€%¹Õ‰…Ñ½É¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥1¥ÑÑ±•%¹Õ‰ÕÍ¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€1¥ÑÑ±•%¹Õ‰ÕÍ¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥%¹Õ‰ÕÍ¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€%¹Õ‰ÕÍ¹¥µ%¹™½Í}%¹¥Ð ¤ì(€€€•áÑ•É¸Ù½¥U¹­­½Ý¸ÈÍ¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€U¹­­½Ý¸ÈÍ¹¥µ%¹™½Í}%¹¥Ð ¤ì((€€€•áÑ•É¸Ù½¥5…ÀÙLÀÑáÑÉ…¹¥µ%¹™½Í}%¹¥Ð¡Ù½¥¤ì(€€€5…ÀÙLÀÑáÑÉ…¹¥µ%¹™½Í}%¹¥Ð ¤ì((€€€€¼¨µ…ÀÝ}ÌÀÌ•¹‘¥¹œ5LÁ¡…Í”Á½¥¹Ñ•ÉÌè|àÀÁÈÌÁmÁ¡…Í•tÍ•±•ÑÌÝ¡¥ L(€€€€€¨‰Õ™™•È¡½±‘ÌÑ¡”…Ñ¥Ù”ÕÑÍ•¹”ÌÉ•™½Éµ…ÑÑ•5L¡•…‘•È¸]…Ì„é•É¼µÍÑÕˆ(€€€€€¨€¡9U10¤Ý¡¥ ™½É•Ñ¡”5LÉ•‘¥É•Ð½¹Ñ¼Ñ¡”Í¥¹±”±…Ñ•ÍÐ}µÍ!•…Á!•…‘•È°(€€€€€¨‘•Íå¹¥¹œÑ¡”µÕ±Ñ¤µÁ¡…Í”•¹‘¥¹œ¸M}	UI|¨…É”}AÍáI…´µÉ•±…Ñ¥Ù”Í¼Ñ¡¥Ì(€€€€€¨µÕÍÐÉÕ¸…™Ñ•ÈAÍá5•µ½Éå}%¹¥Ð€¡…‰½Ù”¤¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸Ù½¥¨|àÀÁÈÌÁlÉtì(€€€€€€€|àÀÁÈÌÁlÁt€ôM}	UI|ÈÀì(€€€€€€€|àÀÁÈÌÁlÅt€ôM}	UI|Äàì(€€€ô((€€€€¼¨%¹¥Ñ¥…±¥é”½Ù•É±…äÁ½¥¹Ñ•ÉÌÑ¼•µÕ±…Ñ•AM`I4€¨¼(¥˜YIM%=9}%L¡)@À¤(€€€}=Ù±å¹…µ¥Œ€€ôAMa}H ÁàÀÀÁ	à¤ì(•±Í”(€€€}=Ù±å¹…µ¥Œ€€ôAMa}H ÁàÀÀÁäÔÜà¤ì(•¹‘¥˜(€€€}=Ù±	½‘åÁÉ½œ€ôAMa}H ÁàÀÀÀÈÑØÀ¤ì(€€€}•µ½}A±…å¥±•	Õ™™•ÉAÑÈ€ô€¡Í}•µ½É…µ•…Ñ„¨¥AMa}H ÁàÀÀÁÕÀÀ¤ì((€€€€¼¨-•å‰½…Éµ…ÁÁ¥¹œ¥ÌÍ•Ð‰äAÍåÉ½ÍÌ‘•™…Õ±ÑÌ¥¸AÍåa}%¹¥Ñ¥…±¥Í”è(€€€€€¨É½ÍÌõ°¥É±”õX°QÉ¥…¹±”õh°MÅÕ…É”õ`°MÑ…ÉÐõ¹Ñ•È°M•±•ÐõMÁ…”(€€€€€¨A…õÉÉ½Ü­•åÌ°0Äõ1M¡¥™Ð°HÄõIM¡¥™Ð°0Èõ1ÑÉ°°HÈõIÑÉ°€¨¼((€€€€¼¨I½ÕÑ”AÍåÉ½ÍÌ±½¥¹œ¥¹Ñ¼½ÕÈM¥±•¹Ñ!¥±°¹±½œ¡…¹‘±”€¡½ÈÍ¥±•¹”¥Ð(€€€€€¨Ý¡•¸•¹…‰±•}‘•‰Õ}±½œôÀ¤	=IAÍåa}%¹¥Ñ¥…±¥Í”°Í¼AÍåÉ½ÍÌ¹•Ù•È(€€€€€¨É•…Ñ•Ì¥ÑÌ½Ý¸€‰M¥±•¹Ð!¥±°¹±½œˆ…¹¹•Ù•È™±½Í•Ì½ÕÈ¡…¹‘±”…Ð(€€€€€¨Í¡ÕÑ‘½Ý¸€¡¥ÐÕÍ•Ñ¼°±•…Ù¥¹œ}M¡•‰Õ1½œ‘…¹±¥¹œ™½È…¹ä±½¥¹œ(€€€€€¨…™Ñ•ÈAÍåa}M¡ÕÑ‘½Ý¸¤¸€¨¼(€€€AÍåa}1½}M•ÑMÑÉ•…´¡}A½¹™¥œ¹•¹…‰±••‰Õ1½œ€ü}M¡•‰Õ1½œ€è9U10¤ì((€€€€¼¨5MµÕÍÐ‰”Í•Ð	=IAÍåa}%¹¥Ñ¥…±¥Í”ƒŠP¥Ð‘É¥Ù•ÌÑ¡”M0µÕ±Ñ¥Í…µÁ±”(€€€€€¨0…ÑÑÉ¥‰ÕÑ•Ì¡½Í•¸…Ð½¹Ñ•áÐµÉ•…Ñ¥½¸Ñ¥µ”€¡¥¹Í¥‘”I}%¹¥Ñ¥…±¥Í•I•¹‘•È¤¸(€€€€€¨%˜Ñ¡”‘É¥Ù•È…¸Ð¡½¹½È¥Ð°AÍåÉ½ÍÌÉ•ÑÉ¥•ÌÝ¥Ñ¡½ÕÐ5M…¹±•…ÉÌ(€€€€€¨}™}µÍ……M…µÁ±•Ì‰…¬Ñ¼€À¸€¨¼(€€€}™}µÍ……M…µÁ±•Ì€ô}A½¹™¥œ¹µÍ……M…µÁ±•Ìì(€€€M!}1= ‰5Mè€•‘àˆ°}™}µÍ……M…µÁ±•Ì¤ì((€€€€¼¨%¹¥Ñ¥…±¥é”AÍåÉ½ÍÌ€¡É•…Ñ•ÌM0ÈÝ¥¹‘½Ü€¬=Á•¹0½¹Ñ•áÐ¤€¨¼(€€€M!}1= ‰%¹¥Ñ¥…±¥é¥¹œAÍåÉ½ÍÌ€¡M0È€¬=Á•¹0¤¸¸¸ˆ¤ì(€€€AÍåa}%¹¥Ñ¥…±¥Í” ‰M¥±•¹Ð!¥±°ˆ°Ý¥¹‘½Ý]¥‘Ñ °Ý¥¹‘½Ý!•¥¡Ð°}A½¹™¥œ¹™Õ±±ÍÉ••¸¤ì((€€€M!}1= ‰AÍåÉ½ÍÌ¥¹¥Ñ¥…±¥é•¸]¥¹‘½Üè€•‘à•ˆ°Ý¥¹‘½Ý]¥‘Ñ °Ý¥¹‘½Ý!•¥¡Ð¤ì((€€€ì(€€€€€€€½¹ÍÐ¡…È¨±}É•¹‘•É•È€ô€¡½¹ÍÐ¡…È¨¥±•ÑMÑÉ¥¹œ¡1}I9IH¤ì(€€€€€€€½¹ÍÐ¡…È¨±}Ù•¹‘½È€€€ô€¡½¹ÍÐ¡…È¨¥±•ÑMÑÉ¥¹œ¡1}Y9=H¤ì(€€€€€€€½¹ÍÐ¡…È¨±}Ù•ÉÍ¥½¸€€ô€¡½¹ÍÐ¡…È¨¥±•ÑMÑÉ¥¹œ¡1}YIM%=8¤ì(€€€€€€€M!}1= ‰0I•¹‘•É•Èè€•Ìˆ°±}É•¹‘•É•È€ü±}É•¹‘•É•È€è€ˆ¡¹Õ±°¤ˆ¤ì(€€€€€€€M!}1= ‰0Y•¹‘½Èè€€€•Ìˆ°±}Ù•¹‘½È€€€ü±}Ù•¹‘½È€€€è€ˆ¡¹Õ±°¤ˆ¤ì(€€€€€€€M!}1= ‰0Y•ÉÍ¥½¸è€€•Ìˆ°±}Ù•ÉÍ¥½¸€€ü±}Ù•ÉÍ¥½¸€€è€ˆ¡¹Õ±°¤ˆ¤ì(€€€ô((€€€€¼¨ÁÁ±ä­•å‰½…É½½¹ÑÉ½±±•È‰¥¹‘¥¹Ì€¬µ½Ù•µ•¹Ð½‘•‰Õœ½ÁÑ¥½¹Ì™É½´½¹™¥œ(€€€€€¨€¡½Ù•ÉÉ¥‘•ÌÑ¡”AÍåÉ½ÍÌ‘•™…Õ±ÑÌÍ•Ð¥¹Í¥‘”AÍåa}%¹¥Ñ¥…±¥Í”¤¸ÁÁ±¥•ÌÑ¡”(€€€€€¨±…ÍÍ¥ŒÍ¡•µ”¡•É”ìA}½¹ÑÉ½±MÑå±•%¹¥ÐÉ”µ…ÁÁ±¥•ÌÑ¡”µ…Ñ¡¥¹œÍ¡•µ”(€€€€€¨½¹”Ñ¡”Í…Ù•…µ•É„ÍÑå±”¥Ì­¹½Ý¸¸€¨¼(€€€A}ÁÁ±åÑ¥Ù•½¹ÑÉ½±M¡•µ” ¤ì((€€€€¼¨ÁÁ±äÑ¡”Í…Ù•½¹ÑÉ½°ÍÑå±”€¬ÁÕ‰±¥Í Ñ¡”ÍÑå±”É•¥ÍÑÉäÑ¼½¹™¥œ¹™œ(€€€€€¨Í¼Ñ¡”±…Õ¹¡•ÈÌ½¹ÑÉ½°MÑå±”‘É½Á‘½Ý¸É•™±•ÑÌÑ¡¥Ì‰Õ¥±¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸Ù½¥A}½¹ÑÉ½±MÑå±•%¹¥Ð¡Ù½¥¤ì(€€€€€€€A}½¹ÑÉ½±MÑå±•%¹¥Ð ¤ì(€€€ô((€€€€¼¨	É¥¹œÑ¡”…µ”Ý¥¹‘½ÜÑ¼Ñ¡”™½É•É½Õ¹½¸±…Õ¹ ¸M¥±•¹Ñ!¥±±A¹•á”¥Ì„(€€€€€¨½¹Í½±”µÍÕ‰ÍåÍÑ•´…ÁÀ°Í¼]¥¹‘½ÝÌÍÁ…Ý¹Ì„½¹Í½±”Ý¥¹‘½Ü…ÐÍÑ…ÉÑÕÀÑ¡…Ð(€€€€€¨É…‰Ì™½ÕÌ‰•™½É”Ñ¡¥ÌM0Ý¥¹‘½Ü•á¥ÍÑÌ€¡…¹°Ý¥Ñ ½¹Í½±”½™˜°¥ÌÑ¡•¸(€€€€€¨É••½¹Í½±”¤¸Q¡”±…Õ¹¡•ÈÌM•Ñ½É•É½Õ¹‘]¥¹‘½ÜÑ…É•ÑÌÑ¡”ÁÉ½•ÍÌœ(€€€€€¨5…¥¹]¥¹‘½Ý!…¹‘±”°Ý¡¥ É•Í½±Ù•ÌÑ¼Ñ¡…Ð½¹Í½±”€¡½Èé•É¼¤°Í¼Ñ¡”…µ”(€€€€€¨Ý¥¹‘½Ü¹•Ù•ÈÉ•±¥…‰±ä•ÑÌ™½ÕÌ¸I…¥Í”½ÕÈ½Ý¸Ý¥¹‘½Ü¡•É”ƒŠPÑ¡”(€€€€€¨±…Õ¹¡•ÈÌ±±½ÝM•Ñ½É•É½Õ¹‘]¥¹‘½ÜÉ…¹Ð±•ÑÌÑ¡¥ÌÑ…­”Ñ¡”™½É•É½Õ¹¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸M1}]¥¹‘½Ü¨}Ý¥¹‘½Üì(€€€€€€€¥˜€¡}Ý¥¹‘½Ü¤(€€€€€€€ì(€€€€€€€€€€€M1}I…¥Í•]¥¹‘½Ü¡}Ý¥¹‘½Ü¤ì(€€€€€€€ô(€€€ô((€€€€¼¨ÁÁ±äÉ•™É•Í É…Ñ”…¹ÙÍå¹Œ™É½´½¹™¥œ¸(€€€€€¨AÍåÉ½ÍÌ‘•™…Õ±ÑÌÑ¼ÙÍå¹Œõ½™˜ìÝ”½Ù•ÉÉ¥‘”Ù¥„M0‘¥É•Ñ±ä¸(€€€€€¨á±ÕÍ¥Ù”™Õ±±ÍÉ••¸½¹±äƒŠP‰½É‘•É±•ÍÌ€¡™Õ±±ÍÉ••¸ôôÈ¤ÉÕ¹Ì…ÐÑ¡”(€€€€€¨‘•Í­Ñ½Àµ½‘”°Ý¡•É”M1}M•Ñ]¥¹‘½Ý¥ÍÁ±…å5½‘”¡…Ì¹¼•™™•Ð¸€¨¼(€€€¥˜€¡}A½¹™¥œ¹É•™É•Í¡I…Ñ”€ø€À€˜˜}A½¹™¥œ¹™Õ±±ÍÉ••¸€ôô€Ä¤(€€€ì(€€€€€€€•áÑ•É¸M1}]¥¹‘½Ü¨}Ý¥¹‘½Üì(€€€€€€€M1}¥ÍÁ±…å5½‘”µ½‘”ì(€€€€€€€¥˜€¡M1}•Ñ]¥¹‘½Ý¥ÍÁ±…å5½‘”¡}Ý¥¹‘½Ü°€™µ½‘”¤€ôô€À¤(€€€€€€€ì(€€€€€€€€€€€µ½‘”¹É•™É•Í¡}É…Ñ”€ô}A½¹™¥œ¹É•™É•Í¡I…Ñ”ì(€€€€€€€€€€€¥˜€¡M1}M•Ñ]¥¹‘½Ý¥ÍÁ±…å5½‘”¡}Ý¥¹‘½Ü°€™µ½‘”¤€ôô€À¤(€€€€€€€€€€€€€€€M!}1= ‰¥ÍÁ±…äµ½‘”Í•ÐÑ¼€•¡èˆ°}A½¹™¥œ¹É•™É•Í¡I…Ñ”¤ì(€€€€€€€€€€€•±Í”(€€€€€€€€€€€€€€€M!}1= ‰…¥±•Ñ¼Í•Ð€•¡è‘¥ÍÁ±…äµ½‘”è€•Ìˆ°}A½¹™¥œ¹É•™É•Í¡I…Ñ”°M1}•ÑÉÉ½È ¤¤ì(€€€€€€€ô(€€€ô(€€€€¼¨‘¥É•ÐM1}1}M•ÑMÝ…Á%¹Ñ•ÉÙ…°¡•É”¥Ì½Ù•ÉÝÉ¥ÑÑ•¸•Ù•Éä™É…µ”‰ä(€€€€€¨AÍåa}	•¥¹M•¹”€¡Ý¡¥ ‘•É¥Ù•ÌÑ¡”¥¹Ñ•ÉÙ…°™É½´}™}ÍÝ…Á%¹Ñ•ÉÙ…°¤°Í¼(€€€€€¨…ÁÁ±äÙÍå¹ŒÑ¡É½Õ Ñ¡…Ð…Ñ”¥¹ÍÑ•…ƒŠPÍ…µ”Á…Ñ Ñ¡”¥¸µ…µ”A=ÁÑ¥½¹Ì(€€€€€¨µ•¹ÔÕÍ•Ì°Í¼‰½½Ð…¹ÉÕ¹Ñ¥µ”ÍÑ…ä½¹Í¥ÍÑ•¹Ð¸€¨¼(€€€AÍåa}ÁÁ±åYÍå¹Œ¡}A½¹™¥œ¹ÙÍå¹Œ¤ì(€€€M!}1= ‰YMå¹Œè€•Ìˆ°}A½¹™¥œ¹ÙÍå¹Œ€„ô€À€ü€‰½¸ˆ€è€‰½™˜ˆ¤ì((€€€€¼¨ÁÁ±äÑ•áÑÕÉ”µ™¥±Ñ•É¥¹œµ½‘”™É½´½¹™¥œè€À€ô¹•¥Ñ¡•È°€Ä€ôAM`(€€€€€¨‘¥Ñ¡•È°€È€ô‰¥±¥¹•…È¸5ÕÑÕ…±±ä•á±ÕÍ¥Ù”ƒŠP‰¥±¥¹•…ÈÍ½™Ñ•¹Ì(€€€€€¨•Ù•ÉåÑ¡¥¹œÝ¡¥±”‘¥Ñ¡•È­••ÁÌÑ¡”½É¥¥¹…°±½½¬‰ÕÐµ…Í­ÌÑ¡”(€€€€€¨Ñ•áÑÕÉ”µÁ…”Í•…´…ÉÑ¥™…ÑÌ…¹…‘‘ÌÑ¡”…ÕÑ¡•¹Ñ¥ŒAM`¹½¥Í”¸€¨¼(€€€ÍÝ¥Ñ €¡}A½¹™¥œ¹ÁÍá¥Ñ¡•È¤ì(€€€…Í”€Äè€}™}ÁÍá¥Ñ¡•È€ô€Äì}™}‰¥±¥¹•…É¥±Ñ•É¥¹œ€ô€Àì‰É•…¬ì(€€€…Í”€Èè€}™}ÁÍá¥Ñ¡•È€ô€Àì}™}‰¥±¥¹•…É¥±Ñ•É¥¹œ€ô€Äì‰É•…¬ì(€€€‘•™…Õ±Ðè}™}ÁÍá¥Ñ¡•È€ô€Àì}™}‰¥±¥¹•…É¥±Ñ•É¥¹œ€ô€Àì‰É•…¬ì(€€€ô(€€€€¼¨5•¹ÕÌ€¼€Éµ½¹±ä™É…µ•Ì€¡}AÍá¥Ñ¡•ÉMÕÁÁÉ•ÍÍ•¤•Ð‰¥±¥¹•…È¥˜•¹…‰±•°(€€€€€¨¥¹‘•Á•¹‘•¹Ð½˜Ñ¡”€ÍÁÍá}‘¥Ñ¡•Èµ½‘”…‰½Ù”¸€¨¼(€€€}™}µ•¹Õ¥±Ñ•È€ô}A½¹™¥œ¹µ•¹Õ¥±Ñ•È€ü€Ä€è€Àì(€€€}™}‘¥Í…‰±•Á…‘5½Ù•µ•¹Ð€ô€Àì€¼¨‘É¥Ù•¸Á•Èµ™É…µ”‰ä…µ•Á±…äÍÑ…Ñ”€¡…µ•}µ…¥¸¹Œ¤Í¼Ñ¡”µÁ…ÍÑ¥±°¹…Ù¥…Ñ•Ìµ•¹ÕÌ€¨¼(€€€M!}1= ‰¥±Ñ•É¥¹œè€•Ìˆ°(€€€€€€€€€€}™}ÁÍá¥Ñ¡•È€ü€‰AM`‘¥Ñ¡•Èˆ€è(€€€€€€€€€€}™}‰¥±¥¹•…É¥±Ñ•É¥¹œ€ü€‰‰¥±¥¹•…Èˆ€è€‰½™˜ˆ¤ì((€€€€¼¨Aa@µ…ÍÑ•È…Ñ”èAÍåÉ½ÍÌ¥Ì½µÁ¥±•Ý¥Ñ UM}Aa@ôÄ°‰ÕÐÑ¡”(€€€€€¨ÉÕ¹Ñ¥µ”Á…Ñ ¥Ì½ÁÐµ¥¸Ù¥„½¹™¥œ¹™œÕÍ•}ÁáÀ¸]¡•¸€À°ÁÉ¥´•µ¥Ð(€€€€€¨ÝÉ¥Ñ•Ì…}éÜôÀ…¹Ñ¡”Ù•ÉÑ•àÍ¡…‘•ÈÑ…­•ÌÑ¡”€Éµ½ÉÑ¡¼‰É…¹ (€€€€€¨€¡AM`µ…™™¥¹”±½½¬¤¸]¡•¸€Ä°Q…ÁÑÕÉ•Ì@ÑÝ¥¹Ì…¹Í¡…‘•È‘½•Ì(€€€€€¨Á•ÉÍÁ•Ñ¥Ù”µ½ÉÉ•ÐÁÉ½©•Ñ¥½¸Ù¥„AÉ½©•Ñ¥½¸Í€¬…¡”±½½­ÕÁÌ¸(€€€€€¨€¡‘•±…É•¥¸AÍå`½AÍåa}ÁÕ‰±¥Œ¹ °‘•™¥¹•¥¸AÍåa}É•¹‘•È¹ÁÀ¤€¨¼(€€€}AÍáUÍ•AáÀ€ô}A½¹™¥œ¹ÕÍ•AáÀ€ü€Ä€è€Àì(€€€M!}1= ‰Aa@è€•Ìˆ°}AÍáUÍ•AáÀ€ü€‰=8€¡Á•ÉÍÁ•Ñ¥Ù”µ½ÉÉ•Ð°]%@¤ˆ€è€‰½™˜€¡…™™¥¹”¤ˆ¤ì((€€€€¼¨Õ±°µÍÉ••¸Á½ÍÐµÁÉ½•ÍÌ±½½¬€¡½±½ÈÉ…‘”€¼IP€¼Í…¹±¥¹•Ì€¼Ù¥¹•ÑÑ”€¼(€€€€€¨É…¥¸€¼Í¡…ÉÁ•¸€¼AM`‘½Ý¹Í…µÁ±”€¼¥¹•µ…Ñ¥Œ¤¸IÕ¹Ñ¥µ”µÍ•ÑÑ…‰±”ìÈå±•Ì(€€€€€¨¥Ð¥¸µ…µ”€¡‘‰}½Ù•É±…ä¹Œ¤¸€¨¼(€€€}™}Á½ÍÑAÉ½•ÍÌ€ô}A½¹™¥œ¹Á½ÍÑAÉ½•ÍÌì(€€€M!}1= ‰A½ÍÐµÁÉ½•ÍÌèµ½‘”€•ˆ°}™}Á½ÍÑAÉ½•ÍÌ¤ì((€€€€¼¨Q½¹”µµ…À½Á•É…Ñ½È½¸Ñ¡”™¥¹…°¥µ…”€ Àõ½™˜°ÄõI•¥¹¡…É°ÈõL°Ìõ¥±µ¥Œ¤¸(€€€€€¨IÕ¹Ñ¥µ”µÍ•ÑÑ…‰±”ìÌå±•Ì¥Ð¥¸µ…µ”€¡‘‰}½Ù•É±…ä¹Œ¤¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸¥¹Ð}™}Ñ½¹•µ…Àì(€€€€€€€}™}Ñ½¹•µ…À€ô}A½¹™¥œ¹Ñ½¹•µ…Àì(€€€€€€€M!}1= ‰Q½¹”µ…ÁÁ¥¹œèµ½‘”€•ˆ°}™}Ñ½¹•µ…À¤ì(€€€ô((€€€€¼¨±…Í¡±¥¡Ðµ½‘”è±…ÍÍ¥Œ€¡AM`Á•ÈµÙ•ÉÑ•à¤€¼±…ÍÍ¥Œ€¬M¡…‘½ÝÌ€¡Á•ÈµÁ¥á•°°(€€€€€¨AM`µ…±¥‰É…Ñ•ÍÑå±”¤€¼5½‘•É¸€¡Á•ÈµÁ¥á•°ÍÑå±¥é•ÍÁ½Ñ±¥¡Ð¤€¼5½‘•É¸€¬(€€€€€¨M¡…‘½ÝÌ¸Ðå±•Ì¥ÐìA=ÁÑ¥½¹Ì€‰±…Í¡±¥¡ÐˆÉ½Üì½¹Í½±”™±µ½‘•€¸(€€€€€¨Q¡”…ÁÁ±ä¡•±Á•È‘•É¥Ù•ÌÑ¡”Á•ÈµÁ¥á•°½ÍÑå±”½Í¡…‘½ÜAÍå`±½‰…±Ì…¹Ñ¡”(€€€€€¨Á•ÈµÍÑå±”¥¹Ñ•¹Í¥Ñä½Í¥é”‘•™…Õ±ÑÌ¸€¨¼(€€€ì(€€€€€€€A}±…Í¡±¥¡Ñ5½‘•ÁÁ±ä¡}A½¹™¥œ¹™±…Í¡±¥¡Ñ5½‘”°€À¤ì(€€€€€€€M!}1= ‰±…Í¡±¥¡Ðµ½‘”è€•Ìˆ°A}±…Í¡±¥¡Ñ5½‘•1…‰•°¡}A½¹™¥œ¹™±…Í¡±¥¡Ñ5½‘”¤¤ì(€€€ô((€€€€¼¨MATMH•¹Ù•±½Á•Ì€¡…ÑÑ…¬½É•±•…Í”¥¹ÍÑÉÕµ•¹Ð™…‘•Ì¥¸Ñ¡”Í•ÅÕ•¹•	4¤(€€€€€¨€¬É•Ù•Éˆ‘•ÁÑ ´ùÝ•ÐÍ…±”¸…‘ÍÈ‘•™…Õ±Ð½¸ì…‘ÍÈ€À¼Å€½¹Í½±”½Ù•ÉÉ¥‘•Ì(€€€€€¨±¥Ù”°É•ÙÍ…±•€ÑÕ¹•ÌÑ¡”É•Ù•Éˆµ…ÁÁ¥¹œ¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸Ù½¥€AÍåa}MAU1}M•Ñ‘ÍÉ¹…‰±•¡¥¹Ð½¸¤ì(€€€€€€€•áÑ•É¸Ù½¥€AÍåa}MAU1}M•ÑI•Ù•É‰•ÁÑ¡M…±”¡™±½…ÐÍ…±”¤ì(€€€€€€€AÍåa}MAU1}M•Ñ‘ÍÉ¹…‰±•¡}A½¹™¥œ¹…‘ÍÈ€ü€Ä€è€À¤ì(€€€€€€€¥˜€¡}A½¹™¥œ¹É•Ù•É‰M…±”€ø€À¸Á˜¤(€€€€€€€€€€€AÍåa}MAU1}M•ÑI•Ù•É‰•ÁÑ¡M…±”¡}A½¹™¥œ¹É•Ù•É‰M…±”¤ì(€€€€€€€M!}1= ‰MATMH•¹Ù•±½Á•Ìè€•Ì°É•Ù•ÉˆÍ…±”€”¸É˜ˆ°(€€€€€€€€€€€€€€}A½¹™¥œ¹…‘ÍÈ€ü€‰=8ˆ€è€‰½™˜ˆ°}A½¹™¥œ¹É•Ù•É‰M…±”¤ì(€€€ô((€€€€¼¨MÁ•…­•È±…å½ÕÐ€¡…Õ‘¥½}½ÕÑÁÕÐ€ô…ÕÑ½ñÍÑ•É•½ñÅÕ…‘ðÔÅðÜÅñ¡ÉÑ˜¤¸5ÕÍÐ‰”(€€€€€¨±…Ñ¡•‰•™½É”MÁÕ%¹¥Ð‰•±½ÜƒŠPÑ¡”=Á•¹0½¹Ñ•áÐ¥ÌÉ•…Ñ•Ñ¡•É”…¹(€€€€€¨…¸•áÁ±¥¥Ð±…å½ÕÐÉ¥‘•Ì¥¸…Ì„½¹Ñ•áÐ…ÑÑÉ¥‰ÕÑ”¸ÕÑ¼Á…ÍÍ•Ì¹¼(€€€€€¨…ÑÑÉ¥‰ÕÑ”Í¼=Á•¹0M½™Ð‘•Ñ•ÑÌÑ¡”ÍåÍÑ•´±…å½ÕÐ¥ÑÍ•±˜¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸Ù½¥AÍåa}MAU1}M•Ñ=ÕÑÁÕÑ5½‘”¡¥¹Ðµ½‘”¤ì(€€€€€€€ÍÑ…Ñ¥Œ½¹ÍÐ¡…È¨½¹ÍÐ­MÁ•…­•É9…µ•Ímt€ôì€‰…ÕÑ¼ˆ°€‰ÍÑ•É•¼ˆ°€‰ÅÕ…ˆ°€ˆÔ¸Äˆ°€ˆÜ¸Äˆ°€‰¡ÉÑ˜ˆôì(€€€€€€€AÍåa}MAU1}M•Ñ=ÕÑÁÕÑ5½‘”¡}A½¹™¥œ¹…Õ‘¥½=ÕÑÁÕÐ¤ì(€€€€€€€M!}1= ‰MÁ•…­•È±…å½ÕÐÉ•ÅÕ•ÍÐè€•Ìˆ°­MÁ•…­•É9…µ•Ím}A½¹™¥œ¹…Õ‘¥½=ÕÑÁÕÑt¤ì(€€€ô((€€€€¼¨™™•Ð¥¹Ñ•¹Í¥Ñ¥•Ì€¡¥¸µ…µ”l±½Ý•ÉÌ€¼tÉ…¥Í•Ì°pÍÝ¥Ñ¡•ÌÝ¡¥ •¹…‰±•(€€€€€¨•™™•Ðì½¹Í½±”™±¥¹Ñ•¹Í¥Ñä€¼Á½ÍÑ¥¹Ñ•¹Í¥Ñä€¼Ñµ¥¹Ñ•¹Í¥Ñä¤¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸™±½…Ð}AÍåa}±…Í¡±¥¡Ñ%¹Ñ•¹Í¥Ñä°}™}Á½ÍÑAÉ½•ÍÍ%¹Ñ•¹Í¥Ñä°}™}Ñ½¹•µ…Á%¹Ñ•¹Í¥Ñäì(€€€€€€€•áÑ•É¸™±½…Ð}AÍåa}±…Í¡±¥¡ÑM¥é”ì(€€€€€€€•áÑ•É¸™±½…Ð}AÍåa}±…Í¡±¥¡Ñ%¹Ñ•¹Í¥ÑåÁÌ°}AÍåa}±…Í¡±¥¡ÑM¥é•ÁÌì(€€€€€€€}AÍåa}±…Í¡±¥¡Ñ%¹Ñ•¹Í¥Ñä€ô}A½¹™¥œ¹™±…Í¡±¥¡Ñ%¹Ñ•¹Í¥Ñäì(€€€€€€€}™}Á½ÍÑAÉ½•ÍÍ%¹Ñ•¹Í¥Ñä€ô}A½¹™¥œ¹Á½ÍÑAÉ½•ÍÍ%¹Ñ•¹Í¥Ñäì(€€€€€€€}™}Ñ½¹•µ…Á%¹Ñ•¹Í¥Ñä€€€€€ô}A½¹™¥œ¹Ñ½¹•µ…Á%¹Ñ•¹Í¥Ñäì(€€€€€€€ì(€€€€€€€€€€€•áÑ•É¸™±½…Ð}™}‰É¥¡Ñ¹•ÍÌ°}™}½¹ÑÉ…ÍÐ°}™}Í…ÑÕÉ…Ñ¥½¸ì(€€€€€€€€€€€}™}‰É¥¡Ñ¹•ÍÌ€ô}A½¹™¥œ¹‰É¥¡Ñ¹•ÍÌì(€€€€€€€€€€€}™}½¹ÑÉ…ÍÐ€€€ô}A½¹™¥œ¹½¹ÑÉ…ÍÐì(€€€€€€€€€€€}™}Í…ÑÕÉ…Ñ¥½¸€ô}A½¹™¥œ¹Í…ÑÕÉ…Ñ¥½¸ì(€€€€€€€ô(€€€€€€€}AÍåa}±…Í¡±¥¡ÑM¥é”€€€€€€ô}A½¹™¥œ¹™±…Í¡±¥¡ÑM¥é”ì(€€€€€€€}AÍåa}±…Í¡±¥¡Ñ%¹Ñ•¹Í¥ÑåÁÌ€ô}A½¹™¥œ¹™±…Í¡±¥¡Ñ%¹Ñ•¹Í¥ÑåÁÌì(€€€€€€€}AÍåa}±…Í¡±¥¡ÑM¥é•ÁÌ€€€€€€ô}A½¹™¥œ¹™±…Í¡±¥¡ÑM¥é•ÁÌì(€€€€€€€M!}1= ‰™™•Ð¥¹Ñ•¹Í¥Ñäè™±…Í¡±¥¡Ð€”¸É˜°Á½ÍÐ€”¸É˜°Ñ½¹•µ…À€”¸É˜ì™±…Í¡±¥¡ÐÍ¥é”€”¸É˜ˆ°(€€€€€€€€€€€€€€}AÍåa}±…Í¡±¥¡Ñ%¹Ñ•¹Í¥Ñä°}™}Á½ÍÑAÉ½•ÍÍ%¹Ñ•¹Í¥Ñä°}™}Ñ½¹•µ…Á%¹Ñ•¹Í¥Ñä°}AÍåa}±…Í¡±¥¡ÑM¥é”¤ì(€€€ô((€€€€¼¨5X½Ù½¥”€¡a¤µ…ÍÑ•ÈÙ½±Õµ”€¡½ÁÑ¥½¹Ìµµ•¹ÔÍ±¥‘•È€¬á…Ù½±Õµ•€½¹Í½±”¤¸(€€€€€¨M•ÐÑ¡”±½‰…°Ñ¡”aÁ±…å•ÈµÕ±Ñ¥Á±¥•Ì¥¹Ñ¼Ñ¡”=Á•¹0Í½ÕÉ”…¥¸¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸™±½…Ð}Aa…Y½±Õµ”ì(€€€€€€€•áÑ•É¸™±½…Ð}AµÙY½±Õµ”ì(€€€€€€€}Aa…Y½±Õµ”€ô}A½¹™¥œ¹á…Y½±Õµ”ì(€€€€€€€}AµÙY½±Õµ”€ô}A½¹™¥œ¹™µÙY½±Õµ”ì(€€€€€€€M!}1= ‰aÙ½¥”Ù½±Õµ”è€”¸É˜°5Xµ½Ù¥”Ù½±Õµ”è€”¸É˜ˆ°}Aa…Y½±Õµ”°}AµÙY½±Õµ”¤ì(€€€ô((€€€€¼¨%¹¥Ñ¥…±¥é”AMdµDÍÕ‰ÍåÍÑ•µÌÙ¥„AÍåÉ½ÍÌ€¨¼(€€€M!}1= ‰%¹¥Ñ¥…±¥é¥¹œAMdµDÍÕ‰ÍåÍÑ•µÌ¸¸¸ˆ¤ì(€€€I•Í•Ñ…±±‰…¬ ¤ì(€€€MÁÕ%¹¥Ð ¤ì((€€€€¼¨%¹¥Ñ¥…±¥é”™¥±•ÍåÍÑ•´€´ÑÉä±½…‘¥¹œ™É½´¥µ…”½È‘¥É•Ñ½Éä€¨¼(€€€M!}1= ‰%¹¥Ñ¥…±¥é¥¹œ™¥±•ÍåÍÑ•´¸¸¸ˆ¤ì(€€€ì(€€€€€€€€¼¨I•Í½±Ù”Ñ¡”‘¥ÍŒ€¡UL½A0¤°Í•±•ÐÑ¡”É•¥½¸Ì™¥±”Ñ…‰±”°…¹½Á•¸¥Ð¸€¨¼(€€€€€€€½¹ÍÐ¡…È¨‘%µ…•A…Ñ €ôAA½ÉÑ}•Ñ…µ•¥ÍA…Ñ  ¤ì((€€€€€€€¥˜€¡‘%µ…•A…Ñ¡lÁt¤ì(€€€€€€€€€€€M!}1= ‰¥µ…”™½Õ¹°¥¹¥Ñ¥…±¥é¥¹œL¸¸¸ˆ¤ì(€€€€€€€€€€€AÍåa}M}%¹¥Ð¡‘%µ…•A…Ñ °€À°€À¤ì(€€€€€€€ô•±Í”ì(€€€€€€€€€€€M!}]I8 ‰…µ”Ý¥±°¹½Ð‰”…‰±”Ñ¼±½……ÍÍ•ÑÌÝ¥Ñ¡½ÕÐ„‘¥ÍŒ¥µ…”¸ˆ¤ì(€€€€€€€ô(€€€ô((€€€€¼¨I•¥½¸µÍÁ•¥™¥Œ‘…Ñ„ÑÝ•…­Ì¹½ÜÑ¡…Ð}…µ•I•¥½¸¥Ì­¹½Ý¸€¡”¹œ¸A0Ì(€€€€€¨É•äµ¡¥±€´ø5Õµ‰±•Èµ½‘•°ÍÝ…À°A0™½¹Ð±…å½ÕÐ½YI4¡½µ”¤¸€¨¼(€€€ì•áÑ•É¸Ù½¥¡…É……Ñ…}ÁÁ±åI•¥½¹A…Ñ¡•Ì¡Ù½¥¤ì¡…É……Ñ…}ÁÁ±åI•¥½¹A…Ñ¡•Ì ¤ìô(€€€ì•áÑ•É¸Ù½¥½¹Ñ}ÁÁ±åI•¥½¹A…Ñ¡•Ì¡Ù½¥¤ì½¹Ñ}ÁÁ±åI•¥½¹A…Ñ¡•Ì ¤ìô(€€€ì•áÑ•É¸Ù½¥A}1…¹%¹¥Ð¡Ù½¥¤ìA}1…¹%¹¥Ð ¤ìô((€€€‘%¹¥Ð ¤ì((€€€€¼¨%¹¥Ñ¥…±¥é”AT€¨¼(€€€M!}1= ‰%¹¥Ñ¥…±¥é¥¹œAT¸¸¸ˆ¤ì(€€€I•Í•ÑÉ…Á  À¤ì(€€€M•ÑÉ…Á¡•‰Õœ À¤ì((€€€€¼¨%¹¥Ñ¥…±¥é”™¥±”ÍåÍÑ•´ÅÕ•Õ”€¨¼(€€€M!}1= ‰%¹¥Ñ¥…±¥é¥¹œ™¥±•ÍåÍÑ•´ÅÕ•Õ”¸¸¸ˆ¤ì(€€€Í}EÕ•Õ•%¹¥Ñ¥…±¥é” ¤ì((€€€€¼¨I…¹‘½µ¥é•Èè™½É•ÌÑ¡”ÍÑ…ÉÐµ…À€¡µ…ÀÉ}ÌÀÐ¤…¹ÑÕÉ¹ÌÑ¡”±½‰…°¡…É„Á½½°(€€€€€¨½¸°Í¼¥ÐµÕÍÐÉÕ¸‰•™½É”5…ÁI•¥ÍÑÉå}%¹¥ÐÉ•…‘Ì}A½¹™¥œ¹µ…Á9…µ”9(€€€€€¨‰•™½É”A}¡…É…±½‰…±}=Á•¸°Ý¡¥ •…É±äµ½ÕÑÌ½¸±½‰…±¡…É…A½½°€ôô€À¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸Ù½¥A}I…¹‘½}%¹¥Ð¡Ù½¥¤ì(€€€€€€€A}I…¹‘½}%¹¥Ð ¤ì(€€€ô((€€€€¼¨±½‰…°¡…É„Á½½°è½Á•¸¡…É…}±½‰…°¹‘±°€¡$ÕÁ‘…Ñ”™Õ¹Ì™½È•Ù•Éä(€€€€€¨Á½ÉÑ…‰±”µ½¹ÍÑ•È¤‰•™½É”Ñ¡”™¥ÉÍÐ5…ÁI•¥ÍÑÉå}1½…Í¼¥ÑÌ‰…­™¥±°(€€€€€¨¡½½¬…¸ÕÍ”¥Ð¸ÍÍ•Ð±½…‘¥¹œ¡…ÁÁ•¹Ì±…Ñ•È°½¸µ…À±½…¸€¨¼(€€€ì(€€€€€€€•áÑ•É¸Ù½¥A}¡…É…±½‰…±}=Á•¸¡Ù½¥¤ì(€€€€€€€A}¡…É…±½‰…±}=Á•¸ ¤ì(€€€ô((€€€€¼¨%¹¥Ñ¥…±¥é”µ…ÀÉ•¥ÍÑÉäƒŠPÍ•ÑÌ}Á5…Á=Ù•É±…å!•…‘•È‰…Í•½¸½¹™¥œ¹™œ¸(€€€€€¨5ÕÍÐ¡…ÁÁ•¸…™Ñ•ÈAA½ÉÑ}%¹¥Ñ¡…É…¹¥µ%¹™¼€¡…¹¥´ÍÑÕ‰Ì¤‰ÕÐ‰•™½É”5…¥¹1½½À¸€¨¼(€€€M!}1= ‰%¹¥Ñ¥…±¥é¥¹œµ…ÀÉ•¥ÍÑÉä¸¸¸ˆ¤ì(€€€5…ÁI•¥ÍÑÉå}%¹¥Ð ¤ì(€€€M!}1= ‰Ñ¥Ù”µ…Àè€•Ìˆ°}A½¹™¥œ¹µ…Á9…µ”¤ì((€€€M!}1= ‰±°ÍÕ‰ÍåÍÑ•µÌ¥¹¥Ñ¥…±¥é•¸¹Ñ•É¥¹œ5…¥¹1½½À¸¸¸ˆ¤ì((€€€€¼¨Q¡”É…Á¡¥Œµ½¹Ñ•¹ÐÝ…É¹¥¹œ€ ‰Q¡•É”…É”Ù¥½±•¹Ð…¹‘¥ÍÑÕÉ‰¥¹œ(€€€€€¨¥µ…•Ì¥¸Ñ¡¥Ì…µ”ˆ¤ÕÍ•Ñ¼™¥É”¡•É”°‰ÕÐ¥ÐÉ…¸‰•™½É”(€€€€€¨5…¥¹1½½ÀÌÍ%¹¥ÑY½Õ¹Ð½%¹¥Ñ•½´½M}%¹¥ÐÍ¼ÍÕ‰Í•ÅÕ•¹Ð‰½½Ð(€€€€€¨ÍÑ…Ñ•Ì€¡-½¹…µ¤°-P¤Í…Ü„¹½Ñ¥•…‰±”±½……À¸5½Ù•¥¹Ñ¼(€€€€€¨5…¥¹1½½ÀÌÍÑ…ÉÑÕÀÁ¡…Í”É¥¡Ð‰•™½É”Ñ¡”…µ”µÍÑ…Ñ”±½½ÀƒŠP(€€€€€¨Í•”ÍÉŒ½‰½‘åÁÉ½œ½ÍåÌ½…µ•}µ…¥¸¹Œ¹•…ÈÑ¡”M}%¹¥Ð‰±½¬¸€¨¼((€€€€¼¨(€€€€€¨=¸AM`°µ…¥¸ ¤±½…‘Ì	=eAI=¹	%8…¹	}-=95$¹	%8½Ù•É±…åÌ°(€€€€€¨Ñ¡•¸…±±Ì5…¥¹1½½À ¤Ý¡¥ ¥Ì¥¸	=eAI=¸(€€€€€¨(€€€€€¨=¸A°•Ù•ÉåÑ¡¥¹œ¥ÌÍÑ…Ñ¥…±±ä±¥¹­•°Í¼Ý”…±°5…¥¹1½½À ¤‘¥É•Ñ±ä¸(€€€€€¨¼(€€€5…¥¹1½½À ¤ì((€€€€¼¨±•…¹ÕÀ€¨¼(€€€M!}	 ‰mM!t5…¥¹1½½À•á¥Ñ•¹½Éµ…±±ä¸M¡ÕÑÑ¥¹œ‘½Ý¸¸¸¸ˆ¤ì(€€€AÍåa}M¡ÕÑ‘½Ý¸ ¤ì((€€€É•ÑÕÉ¸€Àì)ô(