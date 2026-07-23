using System;
using System.Runtime.InteropServices;
using System.Text;

namespace ContextLease
{
    /// <summary>Owns one in-process ContextLease arena backed by the Rust core.</summary>
    public sealed class ContextLeaseArena : IDisposable
    {
        public const uint SupportedAbiVersion = 2;

        private readonly object _sync = new object();
        private IntPtr _handle;
        private NativeMethods.TokenCountCallback? _tokenCountCallback;

        public ContextLeaseArena(string definitionJson)
        {
            if (definitionJson == null) throw new ArgumentNullException(nameof(definitionJson));
            EnsureAbi();

            IntPtr input = Utf8.Alloc(definitionJson);
            try
            {
                Check(NativeMethods.cl_arena_create(input, out _handle));
            }
            finally
            {
                Marshal.FreeHGlobal(input);
            }
        }

        public static uint AbiVersion => NativeMethods.cl_abi_version();

        public static string CoreVersion
        {
            get
            {
                IntPtr value = NativeMethods.cl_core_version();
                try { return Utf8.Read(value); }
                finally { if (value != IntPtr.Zero) NativeMethods.cl_string_free(value); }
            }
        }

        /// <summary>Registers the exact tokenizer used for exact/hybrid count modes.</summary>
        public void SetTokenCounter(Func<string, int> countText)
        {
            if (countText == null) throw new ArgumentNullException(nameof(countText));
            lock (_sync)
            {
                ThrowIfDisposed();
                _tokenCountCallback = (text, _) =>
                {
                    try { return Math.Max(0, countText(Utf8.Read(text))); }
                    catch { return -1; }
                };
                Check(NativeMethods.cl_arena_set_token_counter(_handle, _tokenCountCallback, IntPtr.Zero));
            }
        }

        public string PrepareJson(string requestJson)
        {
            if (requestJson == null) throw new ArgumentNullException(nameof(requestJson));

            lock (_sync)
            {
                ThrowIfDisposed();
                IntPtr input = Utf8.Alloc(requestJson);
                IntPtr output = IntPtr.Zero;
                try
                {
                    Check(NativeMethods.cl_arena_prepare(_handle, input, out output));
                    return Utf8.Read(output);
                }
                finally
                {
                    Marshal.FreeHGlobal(input);
                    if (output != IntPtr.Zero) NativeMethods.cl_string_free(output);
                }
            }
        }

        public string PrepareBeginJson(string requestJson)
        {
            if (requestJson == null) throw new ArgumentNullException(nameof(requestJson));
            lock (_sync)
            {
                ThrowIfDisposed();
                IntPtr input = Utf8.Alloc(requestJson);
                IntPtr output = IntPtr.Zero;
                try
                {
                    Check(NativeMethods.cl_arena_prepare_begin(_handle, input, out output));
                    return Utf8.Read(output);
                }
                finally
                {
                    Marshal.FreeHGlobal(input);
                    if (output != IntPtr.Zero) NativeMethods.cl_string_free(output);
                }
            }
        }

        public string PrepareCommitJson(string requestJson, string semanticResultsJson)
        {
            if (requestJson == null) throw new ArgumentNullException(nameof(requestJson));
            if (semanticResultsJson == null) throw new ArgumentNullException(nameof(semanticResultsJson));
            lock (_sync)
            {
                ThrowIfDisposed();
                IntPtr request = Utf8.Alloc(requestJson);
                IntPtr results = Utf8.Alloc(semanticResultsJson);
                IntPtr output = IntPtr.Zero;
                try
                {
                    Check(NativeMethods.cl_arena_prepare_commit(_handle, request, results, out output));
                    return Utf8.Read(output);
                }
                finally
                {
                    Marshal.FreeHGlobal(request);
                    Marshal.FreeHGlobal(results);
                    if (output != IntPtr.Zero) NativeMethods.cl_string_free(output);
                }
            }
        }

        public string SnapshotJson()
        {
            lock (_sync)
            {
                ThrowIfDisposed();
                IntPtr output = IntPtr.Zero;
                try
                {
                    Check(NativeMethods.cl_arena_snapshot_json(_handle, out output));
                    return Utf8.Read(output);
                }
                finally { if (output != IntPtr.Zero) NativeMethods.cl_string_free(output); }
            }
        }

        public string EventsJson(ulong afterSeq = 0, uint limit = 1000)
        {
            lock (_sync)
            {
                ThrowIfDisposed();
                IntPtr output = IntPtr.Zero;
                try
                {
                    Check(NativeMethods.cl_arena_events_json(_handle, afterSeq, limit, out output));
                    return Utf8.Read(output);
                }
                finally { if (output != IntPtr.Zero) NativeMethods.cl_string_free(output); }
            }
        }

        public string RecordUsageJson(string observationJson)
        {
            if (observationJson == null) throw new ArgumentNullException(nameof(observationJson));
            lock (_sync)
            {
                ThrowIfDisposed();
                IntPtr input = Utf8.Alloc(observationJson);
                IntPtr output = IntPtr.Zero;
                try
                {
                    Check(NativeMethods.cl_arena_record_usage(_handle, input, out output));
                    return Utf8.Read(output);
                }
                finally
                {
                    Marshal.FreeHGlobal(input);
                    if (output != IntPtr.Zero) NativeMethods.cl_string_free(output);
                }
            }
        }

        public void Dispose()
        {
            lock (_sync)
            {
                if (_handle == IntPtr.Zero) return;
                NativeMethods.cl_arena_free(_handle);
                _handle = IntPtr.Zero;
                _tokenCountCallback = null;
            }
            GC.SuppressFinalize(this);
        }

        ~ContextLeaseArena()
        {
            if (_handle != IntPtr.Zero) NativeMethods.cl_arena_free(_handle);
        }

        private static void EnsureAbi()
        {
            uint actual = NativeMethods.cl_abi_version();
            if (actual != SupportedAbiVersion)
            {
                throw new ContextLeaseNativeException(
                    $"Unsupported ContextLease ABI {actual}; expected {SupportedAbiVersion}.");
            }
        }

        private static void Check(int code)
        {
            if (code == 0) return;
            string detail = Utf8.Read(NativeMethods.cl_last_error());
            throw new ContextLeaseNativeException(
                string.IsNullOrEmpty(detail) ? $"ContextLease native error {code}." : detail,
                code);
        }

        private void ThrowIfDisposed()
        {
            if (_handle == IntPtr.Zero) throw new ObjectDisposedException(nameof(ContextLeaseArena));
        }
    }

    public sealed class ContextLeaseNativeException : Exception
    {
        public ContextLeaseNativeException(string message, int errorCode = -1) : base(message)
        {
            ErrorCode = errorCode;
        }

        public int ErrorCode { get; }
    }

    internal static class Utf8
    {
        internal static IntPtr Alloc(string value)
        {
            byte[] bytes = Encoding.UTF8.GetBytes(value + "\0");
            IntPtr pointer = Marshal.AllocHGlobal(bytes.Length);
            Marshal.Copy(bytes, 0, pointer, bytes.Length);
            return pointer;
        }

        internal static string Read(IntPtr pointer)
        {
            if (pointer == IntPtr.Zero) return string.Empty;
            int length = 0;
            while (Marshal.ReadByte(pointer, length) != 0) length++;
            if (length == 0) return string.Empty;
            byte[] bytes = new byte[length];
            Marshal.Copy(pointer, bytes, 0, length);
            return Encoding.UTF8.GetString(bytes);
        }
    }
}
