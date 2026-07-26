# Relevo del port nativo de Silent Hill para Android

Actualizado: 2026-07-26

## Dónde está el trabajo

- Repositorio: https://github.com/YlPorts/silent-hill-decomp
- Rama de trabajo: `codex/android-port-foundation`
- Workflow: `.github/workflows/android.yml`
- Arquitectura objetivo: Android ARM64 (`arm64-v8a`)
- Salida producida: APK debug nativo generado como artefacto de GitHub Actions.

## Estado exacto

- Archivos totales del repositorio: 2,182.
- Tareas de la compilación Android/Ninja: 1,029.
- Última ejecución completada: https://github.com/YlPorts/silent-hill-decomp/actions/runs/30221553172
- Resultado de esa ejecución: 1,029 tareas pasaron, 0 fallaron y 0 quedaron pendientes.
- `Build ARM64 debug APK` y `Upload debug APK` terminaron correctamente.
- Artefacto: `silent-hill-android-debug`, ID `8637381348`, 6,922,782 bytes, SHA-256 del ZIP `2f4152a7bc40884a1ee1c70a66549a79ca005d1dfd23d9967f747bba29e422ae`.
- APK extraído localmente: `outputs/silent-hill-android-debug.apk`, 6,964,363 bytes, SHA-256 `928685eb99df4568bfe7c70f2d6fa944f1612089518d4ff526ef77d7baed1b58`.
- El APK contiene el manifiesto, `libmain.so`, SDL2, OpenAL y 42 bibliotecas de secciones de mapas para `arm64-v8a`; `map0_s00` forma parte del núcleo en vez de una biblioteca de overlay separada.
- La compilación está completa, pero la ejecución aún no está validada: este entorno no tiene `adb` ni emulador Android.

## Cómo calcular el contador sin confundirlo

En el log de Ninja, buscar el mayor valor con formato `[N/1029]` y contar unidades `FAILED:` distintas.

- Pasaron: `N - fallos distintos`.
- Fallaron: cantidad de unidades `FAILED:` distintas.
- No se probaron: `1029 - N`.

No llamar “archivos de código” a las 1,029: son tareas de compilación y enlace. Los 2,182 sí representan el total de archivos del repositorio contado anteriormente.

## Qué debe hacer la siguiente cuenta

1. Abrir la rama `codex/android-port-foundation` y la ejecución exitosa enlazada arriba.
2. Descargar el artefacto `silent-hill-android-debug` si el APK local no está disponible.
3. Conectar un dispositivo/emulador ARM64 y ejecutar `adb install -r silent-hill-android-debug.apk`.
4. Resolver y lanzar la actividad con `adb shell cmd package resolve-activity --brief com.slickamogus.silenthill` y `adb shell am start -n <actividad-resuelta>`.
5. Capturar `adb logcat -b crash`, una captura de pantalla y el árbol de UI durante el primer arranque.
6. Probar selección de datos legales del juego, renderizado, audio, FMV, controles táctiles/físicos, guardado y reanudación.
7. Si aparece un fallo nativo, corregirlo, verificar `git diff --check`, hacer commit/push y repetir la prueba en la misma rama.

## Decisiones técnicas ya tomadas

- Es un port nativo ARM64, no un emulador de PlayStation.
- Los datos comerciales originales del juego no deben incluirse; el usuario tendrá que aportar legalmente sus propios datos.
- SDL2, OpenAL Soft y libjpeg-turbo se obtienen como submódulos fijados.
- PsyCross permanece como submódulo; las diferencias Android se aplican mediante `pc_port/android/patches/psycross-android.patch` en CI.
- El parche PsyCross se aplica con `--ignore-space-change --ignore-whitespace` porque el archivo upstream mezcla convenciones de espacios/finales de línea.
- OpenGL de escritorio se adapta a OpenGL ES 3 en Android.
- Los controles táctiles todavía no están confirmados mediante una prueba real; no prometerlos hasta verificar el APK.

## Riesgos restantes después de compilar

- Fallos de arranque o búsqueda de datos del juego.
- Diferencias de OpenGL ES, audio, FMV, entrada táctil/control físico y guardado.
- `SetMulRotMatrix` todavía tiene una implementación provisional sin efecto en los stubs del port y debe validarse/corregirse durante las pruebas gráficas.
- Rendimiento y compatibilidad entre distintos dispositivos Android.
