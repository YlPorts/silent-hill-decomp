/* PSY-Q to PsyCross compatibility shim */
#ifndef _PSYQ_COMPAT_LIBAPI_H
#define _PSYQ_COMPAT_LIBAPI_H
#include <libapi.h>

#ifdef __ANDROID__
#include <stdint.h>

/* PSX passed 32-bit scratchpad addresses to SetSp. Android uses real 64-bit
 * pointers for the emulated scratchpad, so make the pointer-width conversion
 * explicit before calling PsyCross's compatibility implementation. */
static inline unsigned long PsyqCompat_SetSp(uintptr_t stackPtr)
{
    return SetSp((unsigned long)stackPtr);
}
#define SetSp(stackPtr) PsyqCompat_SetSp((uintptr_t)(stackPtr))
#endif

#endif
