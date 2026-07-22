use contextlease_core::{ArenaDefinition, ContextLeaseArena, PrepareRequest};
use serde::Deserialize;
use std::fs;
use std::path::PathBuf;

#[derive(Deserialize)]
struct Fixture {
    definition: ArenaDefinition,
    request: PrepareRequest,
    #[serde(rename = "assert")]
    expected: Expected,
}

#[derive(Deserialize)]
struct Expected {
    max_prompt_tokens: i32,
    must_contain: Vec<String>,
    lease_borrower: String,
}

#[derive(Deserialize)]
struct ContractFixture {
    arena: ArenaDefinition,
    model: contextlease_core::ModelProfile,
    contributions: Vec<contextlease_core::ModuleContribution>,
}

#[test]
fn shared_basic_borrow_fixture() {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../spec/conformance/basic-borrow.json");
    let fixture: Fixture = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    let result = ContextLeaseArena::new(fixture.definition)
        .unwrap()
        .prepare(fixture.request)
        .unwrap();
    assert!(result.prompt_tokens <= fixture.expected.max_prompt_tokens);
    for term in fixture.expected.must_contain {
        assert!(result.rendered.contains(&term));
    }
    assert!(result
        .leases
        .iter()
        .any(|lease| lease.borrower_module_id == fixture.expected.lease_borrower));
}

#[test]
fn shared_contract_fields_are_preserved() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../spec/conformance/contract-fields.json");
    let fixture: ContractFixture =
        serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    assert_eq!(fixture.arena.modules[0].lifecycle, "session");
    assert_eq!(fixture.arena.modules[0].allocation, "priority");
    assert_eq!(fixture.arena.modules[0].reclaim, "semantic_pipeline");
    assert_eq!(fixture.arena.modules[0].render_target, "messages");
    assert_eq!(fixture.model.count_mode, "hybrid");
    assert_eq!(fixture.contributions[0].chunks[0].kind, "message");
    assert_eq!(fixture.contributions[0].observed_demand_tokens, Some(2));
    assert_eq!(fixture.contributions[0].metadata["producer"], "fixture");
    assert_eq!(
        fixture.contributions[0].chunks[0].metadata["source"],
        "fixture"
    );

    let prepared = ContextLeaseArena::new(fixture.arena)
        .unwrap()
        .prepare(PrepareRequest {
            model: fixture.model,
            contributions: fixture.contributions,
            request_id: Some("contract-rust".into()),
        })
        .unwrap();
    assert_eq!(prepared.token_count_mode, "hybrid");
    assert_eq!(prepared.tokenizer_version, "1");
}

#[test]
fn rust_contract_rejects_unknown_fields() {
    let unknown_arena = r#"{"arena_id":"a","modules":[],"unknown":true}"#;
    let error = serde_json::from_str::<ArenaDefinition>(unknown_arena).unwrap_err();
    assert!(error.to_string().contains("unknown field"));

    let unknown_model = r#"{
        "model_profile_id":"m","context_limit_tokens":8,"reserved_output_tokens":1,
        "unknown":true
    }"#;
    let error = serde_json::from_str::<contextlease_core::ModelProfile>(unknown_model).unwrap_err();
    assert!(error.to_string().contains("unknown field"));
}
