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
/* Return a non-negative token count; return -1 to abort the prepare. */
typedef int32_t (*contextlease_token_count_fn)(const char* text, void* user_data);
enum contextlease_result { CL_OK=0, CL_INVALID_ARGUMENT=1, CL_INVALID_JSON=2,
    CL_CONFIGURATION_ERROR=3, CL_PREPARE_ERROR=4, CL_PANIC=100 };
CL_API uint32_t cl_abi_version(void);
CL_API char* cl_core_version(void);
CL_API int32_t cl_arena_create(const char*, contextlease_arena_t**);
CL_API int32_t cl_arena_prepare(contextlease_arena_t*, const char*, char**);
CL_API int32_t cl_arena_prepare_begin(contextlease_arena_t*, const char*, char**);
CL_API int32_t cl_arena_prepare_commit(contextlease_arena_t*, const char*, const char*, char**);
CL_API int32_t cl_arena_set_token_counter(contextlease_arena_t*, contextlease_token_count_fn, void*);
CL_API int32_t cl_arena_snapshot_json(contextlease_arena_t*, char**);
CL_API int32_t cl_arena_events_json(contextlease_arena_t*, uint64_t after_seq, uint32_t limit, char**);
CL_API int32_t cl_arena_record_usage(contextlease_arena_t*, const char*, char**);
CL_API void cl_arena_free(contextlease_arena_t*);
CL_API void cl_string_free(char*);
CL_API const char* cl_last_error(void);
#ifdef __cplusplus
}
#endif
#endif
