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
