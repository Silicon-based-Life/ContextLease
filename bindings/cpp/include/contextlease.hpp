#pragma once
#include "contextlease.h"
#include <stdexcept>
#include <string>
#include <utility>
namespace contextlease {
class error final : public std::runtime_error { public: using std::runtime_error::runtime_error; };
inline std::string last_error() { const char* value = cl_last_error(); return value ? value : "ContextLease native error"; }
inline std::string core_version() {
    char* value = cl_core_version();
    std::string result(value ? value : "");
    cl_string_free(value);
    return result;
}
class arena final {
public:
    explicit arena(const std::string& definition) {
        if (cl_abi_version() != 2) throw error("Unsupported ContextLease ABI");
        if (cl_arena_create(definition.c_str(), &handle_) != CL_OK) throw error(last_error());
    }
    ~arena() { cl_arena_free(handle_); }
    arena(const arena&) = delete; arena& operator=(const arena&) = delete;
    arena(arena&& other) noexcept : handle_(std::exchange(other.handle_, nullptr)) {}
    std::string prepare(const std::string& request) {
        char* raw = nullptr;
        if (cl_arena_prepare(handle_, request.c_str(), &raw) != CL_OK) throw error(last_error());
        std::string result(raw ? raw : ""); cl_string_free(raw); return result;
    }
    std::string prepare_begin(const std::string& request) {
        char* raw = nullptr;
        if (cl_arena_prepare_begin(handle_, request.c_str(), &raw) != CL_OK) throw error(last_error());
        std::string result(raw ? raw : ""); cl_string_free(raw); return result;
    }
    std::string prepare_commit(const std::string& request, const std::string& semantic_results) {
        char* raw = nullptr;
        if (cl_arena_prepare_commit(handle_, request.c_str(), semantic_results.c_str(), &raw) != CL_OK)
            throw error(last_error());
        std::string result(raw ? raw : ""); cl_string_free(raw); return result;
    }
    void set_token_counter(contextlease_token_count_fn callback, void* user_data = nullptr) {
        if (cl_arena_set_token_counter(handle_, callback, user_data) != CL_OK) throw error(last_error());
    }
    std::string snapshot() {
        char* raw = nullptr;
        if (cl_arena_snapshot_json(handle_, &raw) != CL_OK) throw error(last_error());
        std::string result(raw ? raw : ""); cl_string_free(raw); return result;
    }
    std::string events(uint64_t after_seq = 0, uint32_t limit = 1000) {
        char* raw = nullptr;
        if (cl_arena_events_json(handle_, after_seq, limit, &raw) != CL_OK) throw error(last_error());
        std::string result(raw ? raw : ""); cl_string_free(raw); return result;
    }
    std::string record_usage(const std::string& observation) {
        char* raw = nullptr;
        if (cl_arena_record_usage(handle_, observation.c_str(), &raw) != CL_OK) throw error(last_error());
        std::string result(raw ? raw : ""); cl_string_free(raw); return result;
    }
private: contextlease_arena_t* handle_ = nullptr;
};
}
