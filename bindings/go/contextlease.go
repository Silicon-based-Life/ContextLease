// Package contextlease exposes the ContextLease Rust core to Go through cgo.
package contextlease

/*
#cgo CFLAGS: -I${SRCDIR}/../c/include
#cgo windows LDFLAGS: -L${SRCDIR}/native/windows-x86_64 -lcontextlease_native
#cgo linux LDFLAGS: -L${SRCDIR}/native/linux-x86_64 -lcontextlease_native
#cgo darwin LDFLAGS: -L${SRCDIR}/native/macos-universal -lcontextlease_native
#include <stdlib.h>
#include "contextlease.h"
*/
import "C"

import (
	"errors"
	"runtime"
	"sync"
	"unsafe"
)

const SupportedABIVersion uint32 = 1

// Arena owns one native arena handle. Prepare is serialized per arena.
type Arena struct {
	mu     sync.Mutex
	handle *C.contextlease_arena_t
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

// Close releases the native arena. It is safe to call more than once.
func (a *Arena) Close() {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.handle == nil {
		return
	}
	C.cl_arena_free(a.handle)
	a.handle = nil
	runtime.SetFinalizer(a, nil)
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
