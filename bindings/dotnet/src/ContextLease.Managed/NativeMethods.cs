using System;
using System.Runtime.InteropServices;

namespace ContextLease
{
internal static class NativeMethods
{
    internal const string LibraryName = "contextlease_native_abi2_v0_3_0";

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    internal delegate int TokenCountCallback(IntPtr textUtf8, IntPtr userData);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern uint cl_abi_version();

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern IntPtr cl_core_version();

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_create(IntPtr definitionJsonUtf8, out IntPtr arena);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_prepare(IntPtr arena, IntPtr requestJsonUtf8, out IntPtr resultJsonUtf8);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_prepare_begin(IntPtr arena, IntPtr requestJsonUtf8, out IntPtr resultJsonUtf8);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_prepare_commit(
        IntPtr arena,
        IntPtr requestJsonUtf8,
        IntPtr semanticResultsJsonUtf8,
        out IntPtr resultJsonUtf8);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_snapshot_json(IntPtr arena, out IntPtr resultJsonUtf8);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_events_json(IntPtr arena, ulong afterSeq, uint limit, out IntPtr resultJsonUtf8);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_record_usage(IntPtr arena, IntPtr observationJsonUtf8, out IntPtr resultJsonUtf8);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern int cl_arena_set_token_counter(IntPtr arena, TokenCountCallback callback, IntPtr userData);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern void cl_arena_free(IntPtr arena);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern void cl_string_free(IntPtr value);

    [DllImport(LibraryName, CallingConvention = CallingConvention.Cdecl)]
    internal static extern IntPtr cl_last_error();
}
}
