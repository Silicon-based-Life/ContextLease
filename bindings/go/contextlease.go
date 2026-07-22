// Package contextlease exposes the ContextLease Rust core to Go through cgo.
package contextlease

/*
#cgo CFLAGS: -I${SRCDIR}/../c/include
#cgo windows LDFLAGS: -L${SRCDIR}/native/windows-x86_64 -lcontextlease_native
#cgo linux LDFLAGS: -L${SRCDIR}/native/linux-x86_64 -lcontextlease_native
#cgo darwin LDFLAGS: -L${SRCDIR}/native/macos-universal -lcontextlease_native
#include <stdlib.h>
#include "contextlease.h"
#include "token_callback.h"
*/
import "C"

import (
	"errors"
	"runtime"
	"sync"
	"sync/atomic"
	"unsafe"
)

const SupportedABIVersion uint32 = 2

// Arena owns one native arena handle. Prepare is serialized per arena.
type Arena struct {
	mu          sync.Mutex
	handle      *C.contextlease_arena_t
	counterID   uint64
	counterData unsafe.Pointer
}

var tokenCounters sync.Map
var nextTokenCounterID atomic.Uint64

//export contextlease_go_token_count
func contextlease_go_token_count(text *C.char, userData unsafe.Pointer) (result C.int32_t) {
	defer func() {
		if recover() != nil {
			result = -1
		}
	}()
	if userData == nil {
		return 0
	}
	id := uint64(*(*C.uint64_t)(userData))
	value, ok := tokenCounters.Load(id)
	if !ok {
		return 0
	}
	count := value.(func(string) int)(C.GoString(text))
	if count < 0 {
		return -1
	}
	if count > int(^uint32(0)>>1) {
		count = int(^uint32(0) >> 1)
	}
	return C.int32_t(count)
}

// NewArena creates an arena from a UTF-8 JSON definition.
func NewArena(definitionJSON []byte) (*Arena, error) {
	if ABIVersion() != SupportedABIVersion {
		return nil, errors.New("contextlease: unsupported native ABI")
	}
	input := C.CString(string(definitionJSON))
	defer C.free(unsafe.Pointer(input))
	var handle *C.contextlease_arena_t
	if code := C.cl_arena_create(input, &handle); code != 0 {
		return nil, nativeError(code)
	}
	arena := &Arena{handle: handle}
	runtime.SetFinalizer(arena, (*Arena).Close)
	return arena, nil
}

// ABIVersion returns the loaded native library's ABI version.
func ABIVersion() uint32 { return uint32(C.cl_abi_version()) }

// Prepare applies allocation, leasing, reclaim, and compression to a JSON request.
func (a *Arena) Prepare(requestJSON []byte) ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return nil, errors.New("contextlease: arena is closed")
	}
	input := C.CString(string(requestJSON))
	defer C.free(unsafe.Pointer(input))
	var output *C.char
	if code := C.cl_arena_prepare(a.handle, input, &output); code != 0 {
		return nil, nativeError(code)
	}
	defer C.cl_string_free(output)
	return []byte(C.GoString(output)), nil
}

// SetTokenCounter registers the exact tokenizer used by exact/hybrid plans.
// The callback is synchronous and must not re-enter the same Arena.
func (a *Arena) SetTokenCounter(counter func(string) int) error {
	if counter == nil {
		return errors.New("contextlease: token counter is nil")
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return errors.New("contextlease: arena is closed")
	}
	id := nextTokenCounterID.Add(1)
	data := C.malloc(C.size_t(unsafe.Sizeof(C.uint64_t(0))))
	if data == nil {
		return errors.New("contextlease: token counter allocation failed")
	}
	*(*C.uint64_t)(data) = C.uint64_t(id)
	tokenCounters.Store(id, counter)
	if code := C.cl_arena_set_token_counter(
		a.handle,
		C.contextlease_go_token_count_callback(),
		data,
	); code != 0 {
		tokenCounters.Delete(id)
		C.free(data)
		return nativeError(code)
	}
	a.releaseTokenCounter()
	a.counterID = id
	a.counterData = data
	return nil
}

// PrepareBegin returns either a ready prepared result or host semantic requests.
func (a *Arena) PrepareBegin(requestJSON []byte) ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return nil, errors.New("contextlease: arena is closed")
	}
	input := C.CString(string(requestJSON))
	defer C.free(unsafe.Pointer(input))
	var output *C.char
	if code := C.cl_arena_prepare_begin(a.handle, input, &output); code != 0 {
		return nil, nativeError(code)
	}
	defer C.cl_string_free(output)
	return []byte(C.GoString(output)), nil
}

// PrepareCommit validates host provider results and completes the transaction.
func (a *Arena) PrepareCommit(requestJSON, semanticResultsJSON []byte) ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return nil, errors.New("contextlease: arena is closed")
	}
	request := C.CString(string(requestJSON))
	results := C.CString(string(semanticResultsJSON))
	defer C.free(unsafe.Pointer(request))
	defer C.free(unsafe.Pointer(results))
	var output *C.char
	if code := C.cl_arena_prepare_commit(a.handle, request, results, &output); code != 0 {
		return nil, nativeError(code)
	}
	defer C.cl_string_free(output)
	return []byte(C.GoString(output)), nil
}

// Snapshot returns the latest content-free native snapshot as JSON (`null` before prepare).
func (a *Arena) Snapshot() ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return nil, errors.New("contextlease: arena is closed")
	}
	var output *C.char
	if code := C.cl_arena_snapshot_json(a.handle, &output); code != 0 {
		return nil, nativeError(code)
	}
	defer C.cl_string_free(output)
	return []byte(C.GoString(output)), nil
}

// Events returns content-free native events after the given sequence.
func (a *Arena) Events(afterSeq uint64, limit uint32) ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return nil, errors.New("contextlease: arena is closed")
	}
	var output *C.char
	if code := C.cl_arena_events_json(a.handle, C.uint64_t(afterSeq), C.uint32_t(limit), &output); code != 0 {
		return nil, nativeError(code)
	}
	defer C.cl_string_free(output)
	return []byte(C.GoString(output)), nil
}

// RecordUsage calibrates future estimated/hybrid counts using provider-reported usage JSON.
func (a *Arena) RecordUsage(observationJSON []byte) ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return nil, errors.New("contextlease: arena is closed")
	}
	input := C.CString(string(observationJSON))
	defer C.free(unsafe.Pointer(input))
	var output *C.char
	if code := C.cl_arena_record_usage(a.handle, input, &output); code != 0 {
		return nil, nativeError(code)
	}
	defer C.cl_string_free(output)
	return []byte(C.GoString(output)), nil
}

// Close releases the native arena. It is safe to call more than once.
func (a *Arena) Close() {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return
	}
	C.cl_arena_free(a.handle)
	a.handle = nil
	a.releaseTokenCounter()
	runtime.SetFinalizer(a, nil)
}

func (a *Arena) releaseTokenCounter() {
	if a.counterID != 0 {
		tokenCounters.Delete(a.counterID)
		a.counterID = 0
	}
	if a.counterData != nil {
		C.free(a.counterData)
		a.counterData = nil
	}
}

type nativeCodeError struct {
	code int32
	text string
}

func (e *nativeCodeError) Error() string { return e.text }

func nativeError(code C.int32_t) error {
	text := C.GoString(C.cl_last_error())
	if text == "" {
		text = "contextlease: native error"
	}
	return &nativeCodeError{code: int32(code), text: text}
}
