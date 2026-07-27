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

# Keep the marker so a :game process death returns with the last native stage.
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
            case "FIRST_FRAME_DRAW_OT0": return "entrada al dibujo del fondo y objetos";
            case "FIRST_FRAME_DEPTH_CLEAR": return "limpieza de profundidad OpenGL ES";
            case "FIRST_FRAME_PARSE_OT": return "entrada a la tabla de dibujo";
            case "FIRST_FRAME_BEGIN_SCENE": return "preparación del framebuffer";
            case "FIRST_FRAME_BEGIN_SCENE_READY": return "framebuffer preparado; iniciando primitivas";
            case "FIRST_FRAME_OT_WALK": return "recorrido de las primitivas de PlayStation";
            case "FIRST_FRAME_OT_WALK_READY": return "primitivas procesadas; preparando vértices";
            case "FIRST_FRAME_DRAW_SPLITS": return "subida de vértices y dibujo de lotes OpenGL ES";
            case "FIRST_FRAME_DRAW_SPLITS_READY": return "primer lote gráfico completado";
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
    "describe precise GLES ordering-table stages",
)

# Existing installations retain config.cfg. Force a lightweight compatibility
# profile until the base Android renderer is stable.
text = replace_once(
    text,
    '''            String original = new String(Files.readAllBytes(config.toPath()), StandardCharsets.UTF_8);
            String updated = original.replaceAll(
                    "(?m)^\\s*global_chara_pool\\s*=\\s*[^\\r\\n]+$",
                    "global_chara_pool = 0");
            if (!updated.contains("global_chara_pool = 0")) {
                updated = updated + (updated.endsWith("\\n") ? "" : "\\n")
                        + "global_chara_pool = 0\\n";
            }
''',
    '''            String original = new String(Files.readAllBytes(config.toPath()), StandardCharsets.UTF_8);
            String updated = original;
            String[][] safeValues = {
                    {"global_chara_pool", "0"},
                    {"use_pgxp", "0"},
                    {"post_process", "0"},
                    {"tonemap", "0"},
                    {"flashlight_mode", "0"},
                    {"texture_packs", "0"},
                    {"msaa_samples", "0"}
            };
            for (String[] pair : safeValues) {
                String line = pair[0] + " = " + pair[1];
                String pattern = "(?m)^\\s*" + pair[0] + "\\s*=\\s*[^\\r\\n]+$";
                if (updated.matches("(?s).*" + pattern + ".*")) {
                    updated = updated.replaceAll(pattern, java.util.regex.Matcher.quoteReplacement(line));
                } else {
                    updated = updated + (updated.endsWith("\\n") ? "" : "\\n") + line + "\\n";
                }
            }
''',
    "enforce lightweight Android renderer configuration",
)

LAUNCHER.write_text(text, encoding="utf-8")
print("Android launcher crash diagnostics prepared successfully.")
