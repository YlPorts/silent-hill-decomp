#pragma once

/* The PsyCross Android platform header exposes the formatted eprintinfof /
 * eprintwarnf aliases but a few controller paths use their historical
 * non-suffixed names. Desktop headers provide both. Keep the upstream
 * submodule immutable and supply the missing Android aliases at compile time. */
#ifdef __ANDROID__
#include <android/log.h>

#ifndef eprintinfo
#define eprintinfo(...) \
    __android_log_print(ANDROID_LOG_INFO, "[PsyX] [INFO]", __VA_ARGS__)
#endif
#ifndef eprintwarn
#define eprintwarn(...) \
    __android_log_print(ANDROID_LOG_WARN, "[PsyX] [WARN]", __VA_ARGS__)
#endif
#endif
