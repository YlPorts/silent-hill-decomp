# Relevo del port nativo de Silent Hill para Android

Actualizado: 2026-07-26

## Dónde está el trabajo

- Repositorio: https://github.com/YlPorts/silent-hill-decomp
- Rama de trabajo: `codex/android-port-foundation`
- Workflow: `.github/workflows/android.yml`
- Arquitectura objetivo: Android ARM64 (`arm64-v8a`)
- Salida prevista: APK debug nativo generado como artefacto de GitHub Actions.

## Estado exacto

- Archivos totales del repositorio: 2,182.
- Tareas de la compilación Android/Ninja: 1,029.
- Última ejecución completada: https://github.com/YlPorts/silent-hill-decomp/actions/runs/30221073226
- Resultado de esa ejecución: 1,017 tareas pasaron, 2 fallaron y 10 no llegaron a ejecutarse.
- Los fallos son `Chara_Incubus.c.o` y `Chara_Unknown23.c.o`, ambos por `func_8004C328` y `abs` sin declaraciones visibles.
- La corrección local incluye `item_screens.h` y `<stdlib.h>` en ambas fuentes; debe verificarse en la ejecución siguiente.
- Todavía no existe un APK válido. La compilación no ha llegado a `1029/1029`.

Los 10 pendientes no son 10 errores. Ninja se detiene al encontrar un fallo; la mayoría de las tareas pendientes puede pasar sin cambios cuando llegue su turno.

## Cómo calcular el contador sin confundirlo

En el log de Ninja, buscar el mayor valor con formato `[N/1029]` y contar unidades `FAILED:` distintas.

- Pasaron: `N - fallos distintos`.
- Fallaron: cantidad de unidades `FAILED:` distintas.
- No se probaron: `1029 - N`.

No llamar “archivos de código” a las 1,029: son tareas de compilación y enlace. Los 2,182 sí representan el total de archivos del repositorio contado anteriormente.

## Qué debe hacer la siguiente cuenta

1. Abrir la rama `codex/android-port-foundation` y revisar el workflow Android más reciente.
2. Si falla, descargar/leer el log del job `build-debug-apk`.
3. Calcular el contador con la fórmula anterior y comunicar las tres cifras.
4. Corregir solamente los errores explícitos de Clang/GLES, verificar `git diff --check`, hacer commit y push a la misma rama.
5. Repetir hasta que Ninja complete `1029/1029` y GitHub suba `silent-hill-android-debug`.
6. Después de compilar, probar el APK en un dispositivo/emulador Android: arranque, selección de datos, renderizado, audio, video, controles, guardado y reanudación.

## Decisiones técnicas ya tomadas

- Es un port nativo ARM64, no un emulador de PlayStation.
- Los datos comerciales originales del juego no deben incluirse; el usuario tendrá que aportar legalmente sus propios datos.
- SDL2, OpenAL Soft y libjpeg-turbo se obtienen como submódulos fijados.
- PsyCross permanece como submódulo; las diferencias Android se aplican mediante `pc_port/android/patches/psycross-android.patch` en CI.
- El parche PsyCross se aplica con `--ignore-space-change --ignore-whitespace` porque el archivo upstream mezcla convenciones de espacios/finales de línea.
- OpenGL de escritorio se adapta a OpenGL ES 3 en Android.
- Los controles táctiles todavía no están confirmados mediante una prueba real; no prometerlos hasta verificar el APK.

## Riesgos restantes después de compilar

- Errores de enlace que aparecen al final de las 1,029 tareas.
- Fallos de arranque o búsqueda de datos del juego.
- Diferencias de OpenGL ES, audio, FMV, entrada táctil/control físico y guardado.
- Rendimiento y compatibilidad entre distintos dispositivos Android.
