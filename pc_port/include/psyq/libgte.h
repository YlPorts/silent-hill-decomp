/* PSY-Q to PsyCross compatibility shim */
#ifndef _PSYQ_COMPAT_LIBGTE_H
#define _PSYQ_COMPAT_LIBGTE_H
#include <libgte.h>

/* PsyCross does not expose several PSY-Q helpers used by the decomp. The
 * native port provides them in math_impl.c and the graphics stubs. */
extern void ReadGeomOffset(int* ofx, int* ofy);
extern int  ReadGeomScreen(void);
extern void ReadLightMatrix(MATRIX* m);
extern void OuterProduct12(VECTOR* v0, VECTOR* v1, VECTOR* out);
extern int  Lzc(long value);
extern void LoadAverageCol(unsigned char* v0, unsigned char* v1, long p0, long p1, unsigned char* out);
extern long VectorNormal(VECTOR* value, VECTOR* out);
extern MATRIX* TransposeMatrix(MATRIX* input, MATRIX* output);
extern VECTOR* Square0(VECTOR* input, VECTOR* output);

/* SquareRoot12: not in PsyCross, implemented in pc_port/src/math_impl.c */
extern int SquareRoot12(int a);
#endif
