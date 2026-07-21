# Android native port status

## Architecture

The Android app reuses the decompiled game code and PsyCross. Desktop builds
remain executables; Android builds the same target as `libmain.so`, entered via
`SDL_main`. PsyCross already selects an OpenGL ES 3 renderer on Android.

PSX map overlays remain separate shared objects. Android packages them as
`libmap0_s01.so`, etc. Each overlay links against `libmain.so`, and `-Bsymbolic`
keeps duplicate map-local PSX globals bound to the correct module. Runtime
loading uses a bare soname so the Android linker resolves the library from the
APK native-library directory.

All writable paths are rooted in `SDL_AndroidGetInternalStoragePath()`. The Java
launcher imports a disc through `ACTION_OPEN_DOCUMENT`; no storage permission
or copyrighted data is included.

## Validation gates

- [x] Android Gradle/CMake project and pinned native dependencies.
- [x] ARM64, API 26+, OpenGL ES 3 target.
- [x] Private disc import and first-run config.
- [x] Multi-touch keyboard-to-PSX control bridge.
- [x] Automated debug-APK build workflow.
- [ ] Install and boot on a physical ARM64 device.
- [ ] Complete title screen and new-game smoke test.
- [ ] Verify every map overlay through at least one transition.
- [ ] Validate suspend/resume, audio focus and app switching.
- [ ] Profile memory, frame pacing, battery and thermal throttling.
- [ ] Validate FMV and XA synchronization on representative devices.
- [ ] Add signed release/AAB packaging only after upstream licensing review.

## Known risks

1. The root repository currently has no explicit software license file. Do not
   publish this port commercially or to an app store without resolving code and
   trademark permissions with the upstream authors and rights holders.
2. Android's dynamic linker is stricter than desktop ELF loaders. The CI build
   verifies link-time resolution, but each overlay still needs device testing.
3. The current mobile target is ARM64 only. 32-bit ARM is intentionally omitted
   because this port already relies on 64-bit pointer/layout fixes.
4. Touch controls synthesize the existing keyboard bindings. Custom in-game
   rebinding can therefore make labels disagree until a native touch-binding
   configuration screen is added.

