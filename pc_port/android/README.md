# Silent Hill Android native port (experimental)

This directory packages the existing C/C++ PC port as an Android ARM64 app. It
does **not** contain Silent Hill game data. On first launch, the app asks the
player to select a legally obtained raw `.bin` dump of their own PlayStation
disc and copies it into Android private storage.

## What is implemented

- Native `libmain.so` entry point through SDL2 `SDLActivity`.
- PsyCross OpenGL ES 3 renderer and OpenAL Soft audio integration.
- All map overlays packaged as `libmap*.so` libraries and loaded by soname.
- Android private paths for `config.cfg`, `gamedata`, logs and saves.
- Storage Access Framework disc picker; no broad storage permission.
- Landscape immersive display and multi-touch controls.
- ARM64 build in GitHub Actions with an installable debug APK artifact.

## Build

Requirements: Android Studio with JDK 17, Android SDK 36, NDK
`27.0.12077973`, and CMake `3.22.1`.

```sh
git submodule update --init --recursive
cd pc_port/android
gradle :app:assembleDebug
```

The APK is written under `app/build/outputs/apk/debug/`. The repository CI also
publishes it as the `silent-hill-android-debug` workflow artifact.

## First run

1. Install the APK on an ARM64 Android 8.0+ device with OpenGL ES 3.
2. Tap **Importar imagen BIN** and choose a raw Silent Hill PSX disc dump.
3. Wait for the private copy to finish, then tap **Jugar**.

The disc image remains in the app's private storage and is removed when the app
is uninstalled. The app never downloads or distributes game data.

## Touch layout

The left virtual stick drives the D-pad. The right side exposes Action, Run,
Aim, Light, Map, Inventory, Pause, L1 and R1. Physical SDL-compatible gamepads
continue to work through PsyCross.

## Scope

This is the Android platform foundation, not a claim that every device and
every gameplay path is already production-ready. Runtime/device validation,
pause/resume hardening, thermal performance, FMV/audio latency and touch-layout
polish are tracked in `docs/ANDROID_PORT_STATUS.md`.

