# Summary providers

ContextLease keeps a stable provider interface and treats every inference client as an adapter. Provider selection is configuration, not an allocator concern.

## Built-in OpenAI-compatible adapter

`OpenAICompatibleSummaryProvider` uses Python's standard HTTP library and has no third-party dependency. `base_url` may be either a version root such as `https://gateway.example/v1` or the full `/chat/completions` URL.

```json
{
  "providers": {
    "fast-summary": {
      "type": "openai-compatible",
      "base_url": "https://gateway.example/v1",
      "model": "fast-model",
      "api_key_env": "SUMMARY_API_KEY",
      "timeout_seconds": 20,
      "extra_body": {"seed": 7}
    }
  }
}
```

Non-local HTTP URLs are rejected unless `allow_insecure_http` is explicitly enabled. Localhost is allowed for local inference servers.

## Optional LiteLLM adapter

`LiteLLMSummaryProvider` imports LiteLLM only when invoked. This keeps the base install dependency-free and lets users choose and audit their own LiteLLM version.

```json
{
  "providers": {
    "router": {
      "type": "litellm",
      "model": "provider/model-name",
      "api_key_env": "SUMMARY_API_KEY",
      "api_base": "https://optional-gateway.example/v1",
      "options": {"num_retries": 2}
    }
  }
}
```

## Custom provider

Implement the `SummaryProvider` protocol and register the instance:

```python
from contextlease.providers import SummaryProviderRegistry

registry = SummaryProviderRegistry()
registry.register(MySummaryProvider(provider_id="private", model="summary-v2"))
arena = ContextLeaseArena(definition, summary_providers=registry)
```

For tests, `CallableSummaryProvider` wraps a local function and never performs network I/O.

## Security rules

- Never put keys, bearer tokens, passwords, or authorization values in config.
- `api_key_env` names an environment variable; its value is read only at call time.
- Do not place secrets in `extra_headers` or provider options.
- Treat model-generated summaries as untrusted candidates; required-term, size, and monotonicity checks still apply.
- Use a final deterministic boundary step when strict admission is more important than graceful failure.

## Portfolio summaries

`builtin.semantic.portfolio.v1` calls each configured provider in a fixed sequence. Candidates missing a required term are rejected. The shortest valid candidate wins, with provider and model identity recorded in trace metadata.

```json
{
  "algorithm_id": "builtin.semantic.portfolio.v1",
  "options": {
    "providers": ["local", "cloud"],
    "instructions": "Preserve decisions, evidence, and unresolved work."
  }
}
```

The first release intentionally uses sequential calls for predictable behavior. Hosts needing parallel fan-out can implement a custom provider that performs routing behind the stable interface.
