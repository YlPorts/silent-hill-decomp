#!/usr/bin/env python3
"""Prepare the Android launcher to report crashes from the isolated game process."""

from pathlib import Path

ANDROID_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (
    ANDROID_ROOT
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "slickamogus"
    / "silenthill"
    / "LauncherActivity.java"
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    print(f"[applied] {label}")
    return text.replace(old, new, 1)


text = LAUNCHER.read_text(encoding="utf-8")

# Reaching MainLoop or even presenting one frame does not prove the process will
# remain alive. Keep the marker until the next launch so a :game process death
# always returns to the launcher with the last persistent native stage.
text = replace_once(
    text,
    '''        if (launchPending && "RUNNING".equals(startupStage)) {
            launchMarkerFile().delete();
            launchPending = false;
        }

''',
    "",
    "preserve crash marker for isolated game process",
)

text = replace_once(
    text,
    '''            case "FILES_READY": return "preparación de archivos privados";
            case "STARTING_GRAPHICS": return "creación de la pantalla OpenGL ES";
            case "GRAPHICS_READY": return "inicialización posterior a los gráficos";
            case "STARTING_DISC": return "lectura de la imagen BIN";
            case "DISC_READY": return "inicialización de los demás subsistemas";
            case "ERROR_GRAPHICS_CONTEXT": return "ERROR: no se pudo crear el contexto OpenGL ES";
            case "RUNNING": return "motor iniciado";
''',
    '''            case "FILES_READY": return "preparación de archivos privados";
            case "STARTING_GRAPHICS": return "creación de la pantalla OpenGL ES";
            case "GRAPHICS_READY": return "inicialización posterior a los gráficos";
            case "STARTING_DISC": return "lectura de la imagen BIN";
            case "DISC_READY": return "inicialización de los demás subsistemas";
            case "ERROR_GRAPHICS_CONTEXT": return "ERROR: no se pudo crear el contexto OpenGL ES";
            case "ENTERING_MAINLOOP": return "entrada a MainLoop";
            case "MAINLOOP_GSINIT": return "inicialización del contador gráfico";
            case "MAINLOOP_MEMCARD": return "inicialización de la tarjeta de memoria";
            case "MAINLOOP_JOY": return "inicialización de controles";
            case "MAINLOOP_GEOMETRY": return "inicialización de geometría";
            case "MAINLOOP_AUDIO": return "inicialización de audio";
            case "MAINLOOP_AUDIO_READY": return "preparación de la primera pantalla";
            case "MAINLOOP_WARNING_SKIPPED": return "advertencia omitida; preparando el bucle del juego";
            case "MAINLOOP_LOOP_READY": return "inicio del primer fotograma";
            case "FIRST_FRAME_INPUT": return "lectura de controles del primer fotograma";
            case "FIRST_FRAME_INPUT_READY": return "lógica previa del primer fotograma";
            case "FIRST_FRAME_STATE_UPDATE": return "actualización del estado inicial del juego";
            case "FIRST_FRAME_STATE_READY": return "preparación del dibujo inicial";
            case "FIRST_FRAME_DRAW_OT0": return "dibujo del fondo y objetos del primer fotograma";
            case "FIRST_FRAME_DRAW_OT2": return "dibujo de la interfaz del primer fotograma";
            case "FIRST_FRAME_PRESENT": return "presentación del primer fotograma en OpenGL ES";
            case "FIRST_FRAME_PRESENTED": return "el primer fotograma se mostró; el cierre ocurrió después";
            case "EXITED_NORMALLY": return "MainLoop terminó normalmente";
            case "CRASH_SIGSEGV": return "FALLO NATIVO SIGSEGV (acceso inválido a memoria)";
            case "CRASH_SIGABRT": return "FALLO NATIVO SIGABRT (el motor abortó)";
            case "CRASH_SIGBUS": return "FALLO NATIVO SIGBUS (acceso de memoria no alineado o inválido)";
            case "CRASH_SIGILL": return "FALLO NATIVO SIGILL (instrucción no válida)";
            case "CRASH_SIGFPE": return "FALLO NATIVO SIGFPE (error aritmético)";
            case "CRASH_SIGNAL": return "FALLO NATIVO por señal desconocida";
            case "RUNNING": return "versión anterior del diagnóstico: entrada al bucle principal";
''',
    "describe precise native startup and signal stages",
)

LAUNCHER.write_text(text, encoding="utf-8")
print("Android launcher crash diagnostics prepared successfully.")
