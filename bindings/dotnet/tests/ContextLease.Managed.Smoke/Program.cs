using System.Text.Json;
using ContextLease;

if (args.Length != 1) throw new ArgumentException("Pass the conformance fixture path.");

using JsonDocument fixture = JsonDocument.Parse(File.ReadAllText(args[0]));
JsonElement root = fixture.RootElement;
string definition = root.GetProperty("definition").GetRawText();
string request = root.GetProperty("request").GetRawText();
JsonElement expected = root.GetProperty("assert");

using var arena = new ContextLeaseArena(definition);
using JsonDocument result = JsonDocument.Parse(arena.PrepareJson(request));
JsonElement prepared = result.RootElement;

if (ContextLeaseArena.AbiVersion != ContextLeaseArena.SupportedAbiVersion)
    throw new InvalidOperationException("ABI version mismatch.");
if (prepared.GetProperty("prompt_tokens").GetInt32() > expected.GetProperty("max_prompt_tokens").GetInt32())
    throw new InvalidOperationException("Prepared prompt exceeds the fixture budget.");
if (!prepared.GetProperty("rendered").GetString()!.Contains(expected.GetProperty("must_contain")[0].GetString()!))
    throw new InvalidOperationException("Pinned fixture content was lost.");
if (!prepared.GetProperty("leases").EnumerateArray().Any(
        lease => lease.GetProperty("borrower_module_id").GetString() == expected.GetProperty("lease_borrower").GetString()))
    throw new InvalidOperationException("Expected lease was not issued.");

Console.WriteLine($"ContextLease .NET smoke passed: ABI={ContextLeaseArena.AbiVersion}, core={ContextLeaseArena.CoreVersion}");

const string semanticDefinition = """
{"arena_id":"dotnet-semantic","modules":[{"module_id":"memory","floor_tokens":0,"target_tokens":1,"max_tokens":8,"reclaim_pipeline":[{"algorithm_id":"builtin.semantic.summary.v1","options":{"provider":"mock"}},{"algorithm_id":"builtin.text.boundary_truncate.v1"}]}]}
""";
const string semanticRequest = """
{"request_id":"dotnet-semantic-r1","model":{"model_profile_id":"tiny","context_limit_tokens":4,"reserved_output_tokens":0},"contributions":[{"module_id":"memory","chunks":[{"chunk_id":"facts","content":"alpha beta gamma delta epsilon zeta","required_terms":["alpha"]}]}]}
""";
using var semanticArena = new ContextLeaseArena(semanticDefinition);
using JsonDocument begin = JsonDocument.Parse(semanticArena.PrepareBeginJson(semanticRequest));
JsonElement semantic = begin.RootElement.GetProperty("semantic_requests")[0];
string semanticResults = JsonSerializer.Serialize(new[]
{
    new
    {
        semantic_request_id = semantic.GetProperty("semantic_request_id").GetString(),
        content = "alpha beta",
    },
});
using JsonDocument committed = JsonDocument.Parse(
    semanticArena.PrepareCommitJson(semanticRequest, semanticResults));
if (!committed.RootElement.GetProperty("rendered").GetString()!.Contains("alpha"))
    throw new InvalidOperationException("Two-phase semantic result lost a required term.");
Console.WriteLine("ContextLease .NET semantic two-phase smoke passed");
