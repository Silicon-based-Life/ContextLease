#include "contextlease.hpp"

#include <string>

int main() {
    bool rejected_invalid = false;
    try {
        contextlease::arena invalid("{");
    } catch (const contextlease::error&) {
        rejected_invalid = true;
    }
    if (!rejected_invalid) return 10;

    const std::string definition =
        R"({"arena_id":"cpp-smoke","modules":[{"module_id":"system","floor_tokens":0,"target_tokens":8,"max_tokens":8}]})";
    const std::string request =
        R"({"request_id":"cpp-smoke-r1","model":{"model_profile_id":"tiny","context_limit_tokens":8,"reserved_output_tokens":0},"contributions":[{"module_id":"system","chunks":[{"chunk_id":"contract","content":"keep contract","fixed":true}]}]})";
    contextlease::arena arena(definition);
    const std::string prepared = arena.prepare(request);
    if (prepared.find("keep contract") == std::string::npos) return 1;
    return arena.events().find("request.prepared") == std::string::npos ? 2 : 0;
}
