#ifndef CONTEXTLEASE_H
#define CONTEXTLEASE_H
#include <stdint.h>
#if defined(_WIN32)
#define CL_API __declspec(dllimport)
#else
#define CL_API
#endif
#ifdef __cplusplus
extern "C" {
#endif
typedef struct ContextLeaseArenaHandle contextlease_arena_t;
enum contextlease_result { CL_OK=0, CL_INVALID_ARGUMENT=1, CL_INVALID_JSON=2,
    CL_CONFIGURATION_ERROR=3, CL_PREPARE_ERROR=4, CL_PANIC=100 };
CL_API uint32_t cl_abi_version(void);
CL_API char* cl_core_version(void);
CL_API int32_t cl_arena_create(const char*, contextlease_arena_t**);
CL_API int32_t cl_arena_prepare(contextlease_arena_t*, const char*, char**);
CL_API int32_t cl_arena_prepare_begin(contextlease_arena_t*, const char*, char**);
CL_API int32_t cl_arena_prepare_commit(contextlease_arena_t*, const char*, const char*, char**);
CL_API void cl_arena_free(contextlease_arena_t*);
CL_API void cl_string_free(char*);
CL_API const char* cl_last_error(void);
#ifdef __cplusplus
}
#endif
#endif
