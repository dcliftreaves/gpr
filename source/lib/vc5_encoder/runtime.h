/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#ifndef GPR_ENCODER_RUNTIME_H
#define GPR_ENCODER_RUNTIME_H
#include <stdlib.h>
#ifndef GPR_ENCODER_FAST_DEFAULT
#define GPR_ENCODER_FAST_DEFAULT 0
#endif
/* Explicit 0 disables an exact optimization; unset uses the build default.
 * Read-only: applications must configure their environment before starting
 * codec threads. The library never changes process-global environment. */
static int gpr_encoder_feature_enabled(const char *name)
{
    const char *value = getenv(name);
    return value ? value[0] != '\0' && value[0] != '0' : GPR_ENCODER_FAST_DEFAULT;
}
#endif
