#include "contextlease.h"

#include <stdint.h>
#include <string.h>

int main(void) {
    const char *definition =
        "{\"arena_id\":\"c-smoke\",\"modules\":[{\"module_id\":\"system\","
        "\"floor_tokens\":0,\"target_tokens\":8,\"max_tokens\":8}]}";
    const char *request =
        "{\"request_id\":\"c-smoke-r1\",\"model\":{\"model_profile_id\":\"tiny\","
        "\"context_limit_tokens\":8,\"reserved_output_tokens\":0},\"contributions\":[{"
        "\"module_id\":\"system\",\"chunks\":[{\"chunk_id\":\"contract\","
        "\"content\":\"keep contract\",\"fixed\":true}]}]}";
    contextlease_arena_t *arena = NULL;
    char *prepared = NULL;
    if (cl_abi_version() != 1) return 1;
    if (cl_arena_create(definition, &arena) != CL_OK) return 2;
    if (cl_arena_prepare(arena, request, &prepared) != CL_OK) {
        cl_arena_free(arena);
        return 3;
    }
    if (prepared == NULL || strstr(prepared, "keep contract") == NULL) {
        cl_string_free(prepared);
        cl_arena_free(arena);
        return 4;
    }
    cl_string_free(prepared);
    cl_arena_free(arena);
    return 0;
}
