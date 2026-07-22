use contextlease_core::{
    ArenaDefinition, ContextLeaseArena, PrepareRequest, SemanticResult, TokenCounter,
    UsageObservation,
};
use serde::Serialize;
use std::cell::RefCell;
use std::ffi::{c_char, c_void, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::sync::atomic::{AtomicBool, Ordering};

pub const ABI_VERSION: u32 = 2;
pub const CL_OK: i32 = 0;
pub const CL_INVALID_ARGUMENT: i32 = 1;
pub const CL_INVALID_JSON: i32 = 2;
pub const CL_CONFIGURATION_ERROR: i32 = 3;
pub const CL_PREPARE_ERROR: i32 = 4;
pub const CL_PANIC: i32 = 100;

thread_local! { static LAST_ERROR: RefCell<CString> = RefCell::new(CString::new("").unwrap()); }

pub type TokenCountCallback = unsafe extern "C" fn(*const c_char, *mut c_void) -> i32;

struct HostTokenCounter {
    callback: TokenCountCallback,
    user_data: *mut c_void,
    failed: AtomicBool,
}

unsafe impl Send for HostTokenCounter {}
unsafe impl Sync for HostTokenCounter {}

impl TokenCounter for HostTokenCounter {
    fn count_text(&self, text: &str) -> i32 {
        let safe = text.replace('\0', "\u{fffd}");
        let value = CString::new(safe).unwrap();
        let result = unsafe { (self.callback)(value.as_ptr(), self.user_data) };
        if result < 0 {
            self.failed.store(true, Ordering::Release);
            -1
        } else {
            result
        }
    }
}

impl HostTokenCounter {
    fn reset(&self) {
        self.failed.store(false, Ordering::Release);
    }

    fn failed(&self) -> bool {
        self.failed.load(Ordering::Acquire)
    }
}

pub struct ArenaHandle {
    core: ContextLeaseArena,
    token_counter: Option<HostTokenCounter>,
}

#[derive(Serialize)]
struct ErrorEnvelope<'a> {
    code: &'a str,
    message: &'a str,
}

fn set_error(code: &str, message: impl AsRef<str>) {
    let payload = serde_json::to_string(&ErrorEnvelope {
        code,
        message: message.as_ref(),
    })
    .unwrap_or_else(|_| "{\"code\":\"ffi_error\",\"message\":\"serialization failed\"}".into())
    .replace('\0', "\\u0000");
    LAST_ERROR.with(|slot| *slot.borrow_mut() = CString::new(payload).unwrap());
}

fn set_json_error(error: serde_json::Error) -> i32 {
    if matches!(error.classify(), serde_json::error::Category::Data) {
        set_error("configuration_error", error.to_string());
        CL_CONFIGURATION_ERROR
    } else {
        set_error("invalid_json", error.to_string());
        CL_INVALID_JSON
    }
}

unsafe fn utf8<'a>(value: *const c_char, name: &str) -> Result<&'a str, i32> {
    if value.is_null() {
        set_error("invalid_argument", format!("{name} is null"));
        return Err(CL_INVALID_ARGUMENT);
    }
    CStr::from_ptr(value).to_str().map_err(|_| {
        set_error("invalid_utf8", name);
        CL_INVALID_ARGUMENT
    })
}

#[no_mangle]
pub extern "C" fn cl_abi_version() -> u32 {
    ABI_VERSION
}

#[no_mangle]
pub extern "C" fn cl_core_version() -> *mut c_char {
    CString::new(contextlease_core::CORE_VERSION)
        .unwrap()
        .into_raw()
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_create(json: *const c_char, out: *mut *mut ArenaHandle) -> i32 {
    if out.is_null() {
        set_error("invalid_argument", "out arena is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| {
        let text = match utf8(json, "definition_json") {
            Ok(v) => v,
            Err(c) => return c,
        };
        let definition: ArenaDefinition = match serde_json::from_str(text) {
            Ok(v) => v,
            Err(e) => return set_json_error(e),
        };
        match ContextLeaseArena::new(definition) {
            Ok(arena) => {
                *out = Box::into_raw(Box::new(ArenaHandle {
                    core: arena,
                    token_counter: None,
                }));
                CL_OK
            }
            Err(e) => {
                set_error(e.code, e.message);
                CL_CONFIGURATION_ERROR
            }
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_prepare(
    arena: *mut ArenaHandle,
    json: *const c_char,
    out: *mut *mut c_char,
) -> i32 {
    if arena.is_null() || out.is_null() {
        set_error("invalid_argument", "arena/result is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| {
        let text = match utf8(json, "request_json") {
            Ok(v) => v,
            Err(c) => return c,
        };
        let request: PrepareRequest = match serde_json::from_str(text) {
            Ok(v) => v,
            Err(e) => return set_json_error(e),
        };
        let handle = &*arena;
        let result = match handle.token_counter.as_ref() {
            Some(counter) => {
                counter.reset();
                let result = handle.core.prepare_with_counter(request, counter);
                if counter.failed() {
                    set_error(
                        "tokenizer_callback_failed",
                        "host tokenizer callback returned an error",
                    );
                    return CL_PREPARE_ERROR;
                }
                result
            }
            None => handle.core.prepare(request),
        };
        match result {
            Ok(result) => match serde_json::to_string(&result) {
                Ok(value) => {
                    *out = CString::new(value).unwrap().into_raw();
                    CL_OK
                }
                Err(e) => {
                    set_error("serialization_error", e.to_string());
                    CL_PREPARE_ERROR
                }
            },
            Err(e) => {
                set_error(e.code, e.message);
                CL_PREPARE_ERROR
            }
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_prepare_begin(
    arena: *mut ArenaHandle,
    json: *const c_char,
    out: *mut *mut c_char,
) -> i32 {
    if arena.is_null() || out.is_null() {
        set_error("invalid_argument", "arena/result is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| {
        let text = match utf8(json, "request_json") {
            Ok(value) => value,
            Err(code) => return code,
        };
        let request: PrepareRequest = match serde_json::from_str(text) {
            Ok(value) => value,
            Err(error) => return set_json_error(error),
        };
        let handle = &*arena;
        let result = match handle.token_counter.as_ref() {
            Some(counter) => {
                counter.reset();
                let result = handle.core.prepare_begin_with_counter(request, counter);
                if counter.failed() {
                    set_error(
                        "tokenizer_callback_failed",
                        "host tokenizer callback returned an error",
                    );
                    return CL_PREPARE_ERROR;
                }
                result
            }
            None => handle.core.prepare_begin(request),
        };
        match result {
            Ok(result) => write_json_result(&result, out),
            Err(error) => {
                set_error(error.code, error.message);
                CL_PREPARE_ERROR
            }
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_prepare_commit(
    arena: *mut ArenaHandle,
    request_json: *const c_char,
    semantic_results_json: *const c_char,
    out: *mut *mut c_char,
) -> i32 {
    if arena.is_null() || out.is_null() {
        set_error("invalid_argument", "arena/result is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| {
        let request_text = match utf8(request_json, "request_json") {
            Ok(value) => value,
            Err(code) => return code,
        };
        let results_text = match utf8(semantic_results_json, "semantic_results_json") {
            Ok(value) => value,
            Err(code) => return code,
        };
        let request: PrepareRequest = match serde_json::from_str(request_text) {
            Ok(value) => value,
            Err(error) => return set_json_error(error),
        };
        let results: Vec<SemanticResult> = match serde_json::from_str(results_text) {
            Ok(value) => value,
            Err(error) => return set_json_error(error),
        };
        let handle = &*arena;
        let result = match handle.token_counter.as_ref() {
            Some(counter) => {
                counter.reset();
                let result = handle
                    .core
                    .prepare_commit_with_counter(request, results, counter);
                if counter.failed() {
                    set_error(
                        "tokenizer_callback_failed",
                        "host tokenizer callback returned an error",
                    );
                    return CL_PREPARE_ERROR;
                }
                result
            }
            None => handle.core.prepare_commit(request, results),
        };
        match result {
            Ok(result) => write_json_result(&result, out),
            Err(error) => {
                set_error(error.code, error.message);
                CL_PREPARE_ERROR
            }
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

unsafe fn write_json_result<T: Serialize>(value: &T, out: *mut *mut c_char) -> i32 {
    match serde_json::to_string(value) {
        Ok(json) => {
            *out = CString::new(json).unwrap().into_raw();
            CL_OK
        }
        Err(error) => {
            set_error("serialization_error", error.to_string());
            CL_PREPARE_ERROR
        }
    }
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_set_token_counter(
    arena: *mut ArenaHandle,
    callback: Option<TokenCountCallback>,
    user_data: *mut c_void,
) -> i32 {
    if arena.is_null() {
        set_error("invalid_argument", "arena is null");
        return CL_INVALID_ARGUMENT;
    }
    catch_unwind(AssertUnwindSafe(|| {
        (*arena).token_counter = callback.map(|callback| HostTokenCounter {
            callback,
            user_data,
            failed: AtomicBool::new(false),
        });
        CL_OK
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_snapshot_json(
    arena: *mut ArenaHandle,
    out: *mut *mut c_char,
) -> i32 {
    if arena.is_null() || out.is_null() {
        set_error("invalid_argument", "arena/result is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| match (*arena).core.snapshot() {
        Ok(snapshot) => write_json_result(&snapshot, out),
        Err(error) => {
            set_error(error.code, error.message);
            CL_PREPARE_ERROR
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_events_json(
    arena: *mut ArenaHandle,
    after_seq: u64,
    limit: u32,
    out: *mut *mut c_char,
) -> i32 {
    if arena.is_null() || out.is_null() {
        set_error("invalid_argument", "arena/result is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| {
        match (*arena).core.events_after(after_seq, limit as usize) {
            Ok(events) => write_json_result(&events, out),
            Err(error) => {
                set_error(error.code, error.message);
                CL_PREPARE_ERROR
            }
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_record_usage(
    arena: *mut ArenaHandle,
    observation_json: *const c_char,
    out: *mut *mut c_char,
) -> i32 {
    if arena.is_null() || out.is_null() {
        set_error("invalid_argument", "arena/result is null");
        return CL_INVALID_ARGUMENT;
    }
    *out = ptr::null_mut();
    catch_unwind(AssertUnwindSafe(|| {
        let text = match utf8(observation_json, "observation_json") {
            Ok(value) => value,
            Err(code) => return code,
        };
        let observation: UsageObservation = match serde_json::from_str(text) {
            Ok(value) => value,
            Err(error) => return set_json_error(error),
        };
        match (*arena).core.record_usage(observation) {
            Ok(calibration) => write_json_result(&calibration, out),
            Err(error) => {
                set_error(error.code, error.message);
                CL_PREPARE_ERROR
            }
        }
    }))
    .unwrap_or_else(|_| {
        set_error("panic", "panic contained at FFI boundary");
        CL_PANIC
    })
}

#[no_mangle]
pub unsafe extern "C" fn cl_arena_free(arena: *mut ArenaHandle) {
    if !arena.is_null() {
        drop(Box::from_raw(arena));
    }
}

#[no_mangle]
pub unsafe extern "C" fn cl_string_free(value: *mut c_char) {
    if !value.is_null() {
        drop(CString::from_raw(value));
    }
}

#[no_mangle]
pub extern "C" fn cl_last_error() -> *const c_char {
    LAST_ERROR.with(|slot| slot.borrow().as_ptr())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CString;
    #[test]
    fn missing_required_fields_are_configuration_errors() {
        let json = CString::new("{}").unwrap();
        let mut arena = ptr::null_mut();
        assert_eq!(
            unsafe { cl_arena_create(json.as_ptr(), &mut arena) },
            CL_CONFIGURATION_ERROR
        );
        assert!(arena.is_null());
    }

    #[test]
    fn malformed_json_is_reported_separately() {
        let json = CString::new("{").unwrap();
        let mut arena = ptr::null_mut();
        assert_eq!(
            unsafe { cl_arena_create(json.as_ptr(), &mut arena) },
            CL_INVALID_JSON
        );
        assert!(arena.is_null());
    }

    #[test]
    fn unknown_fields_are_configuration_errors() {
        let json = CString::new(r#"{"arena_id":"a","modules":[],"unknown":true}"#).unwrap();
        let mut arena = ptr::null_mut();
        assert_eq!(
            unsafe { cl_arena_create(json.as_ptr(), &mut arena) },
            CL_CONFIGURATION_ERROR
        );
        assert!(arena.is_null());
        let error = unsafe { CStr::from_ptr(cl_last_error()) }.to_str().unwrap();
        assert!(error.contains("configuration_error"));
        assert!(error.contains("unknown field"));
    }
}
