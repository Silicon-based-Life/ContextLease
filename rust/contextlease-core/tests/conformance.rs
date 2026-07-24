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

#[derive(Deserialize)]
struct RuntimeCases {
    cases: Vec<RuntimeCase>,
}

#[derive(Deserialize)]
struct RuntimeCase {
    name: String,
    definition: ArenaDefinition,
    request: PrepareRequest,
    #[serde(rename = "assert")]
    expected: RuntimeExpected,
}

#[derive(Deserialize)]
struct RuntimeExpected {
    max_prompt_tokens: i32,
    #[serde(default)]
    input_budget_tokens: Option<i32>,
    #[serde(default)]
    must_contain: Vec<String>,
    #[serde(default)]
    expected_modules: Vec<String>,
    #[serde(default)]
    lease_borrower: Option<String>,
    #[serde(default)]
    render_order: Vec<String>,
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
            schema_version: "1.0".into(),
            model: fixture.model,
            contributions: fixture.contributions,
            request_id: Some("contract-rust".into()),
        })
        .unwrap();
    assert_eq!(prepared.token_count_mode, "hybrid");
    assert_eq!(prepared.tokenizer_version, "1");
}

#[test]
fn shared_runtime_cases_match_contract() {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../spec/conformance/runtime-cases.json");
    let fixture: RuntimeCases = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();
    assert!(fixture.cases.len() >= 8);
    for case in fixture.cases {
        let prepared = ContextLeaseArena::new(case.definition)
            .unwrap_or_else(|error| panic!("{} arena failed: {error}", case.name))
            .prepare(case.request)
            .unwrap_or_else(|error| panic!("{} prepare failed: {error}", case.name));
        assert!(
            prepared.prompt_tokens <= case.expected.max_prompt_tokens,
            "{} exceeded prompt budget",
            case.name
        );
        if let Some(expected_budget) = case.expected.input_budget_tokens {
            assert_eq!(
                expected_budget, prepared.input_budget_tokens,
                "{} input budget drifted",
                case.name
            );
        }
        for term in case.expected.must_contain {
            assert!(
                prepared.rendered.contains(&term),
                "{} lost required content {term}",
                case.name
            );
        }
        let module_ids: Vec<&str> = prepared
            .module_plans
            .iter()
            .map(|item| item.module_id.as_str())
            .collect();
        let expected_modules: Vec<&str> = case
            .expected
            .expected_modules
            .iter()
            .map(String::as_str)
            .collect();
        assert_eq!(
            expected_modules, module_ids,
            "{} module order drifted",
            case.name
        );
        if let Some(borrower) = case.expected.lease_borrower {
            assert!(
                prepared
                    .leases
                    .iter()
                    .any(|lease| lease.borrower_module_id == borrower),
                "{} did not issue the expected lease",
                case.name
            );
        }
        let positions: Vec<usize> = case
            .expected
            .render_order
            .iter()
            .map(|value| {
                prepared
                    .rendered
                    .find(value)
                    .unwrap_or_else(|| panic!("{} did not render {value}", case.name))
            })
            .collect();
        assert!(
            positions.windows(2).all(|pair| pair[0] <= pair[1]),
            "{} render order drifted",
            case.name
        );
    }
}

#[test]
fn budget_invariants_hold_across_small_profiles() {
    for context_limit in 1..=24 {
        for reserve in 0..context_limit {
            let input_budget = context_limit - reserve;
            let definition = ArenaDefinition {
                arena_id: format!("invariant-{context_limit}-{reserve}"),
                modules: vec![contextlease_core::ModuleDefinition {
                    module_id: "memory".into(),
                    floor_tokens: 0,
                    target_tokens: input_budget,
                    max_tokens: input_budget,
                    order: 0,
                    weight: 1.0,
                    lifecycle: "request".into(),
                    allocation: "weighted".into(),
                    protection: "mixed".into(),
                    reclaim: "builtin_pipeline".into(),
                    render_target: "text".into(),
                    can_borrow: false,
                    can_lend: true,
                    reclaim_pipeline: vec![contextlease_core::CompressionStepSpec {
                        algorithm_id: "builtin.text.boundary_truncate.v1".into(),
                        options: Default::default(),
                    }],
                    metadata: Default::default(),
                }],
                schema_version: "1.0".into(),
                policy_version: "policy-v1".into(),
                framework_reserve_tokens: 0,
                admission_policy: "reject".into(),
                metadata: Default::default(),
            };
            let prepared = ContextLeaseArena::new(definition)
                .unwrap()
                .prepare(PrepareRequest {
                    schema_version: "1.0".into(),
                    model: contextlease_core::ModelProfile {
                        model_profile_id: "invariant".into(),
                        context_limit_tokens: context_limit,
                        reserved_output_tokens: reserve,
                        tokenizer_id: "estimator".into(),
                        tokenizer_version: "1".into(),
                        count_mode: "estimated".into(),
                    },
                    contributions: vec![contextlease_core::ModuleContribution {
                        module_id: "memory".into(),
                        chunks: vec![contextlease_core::PromptChunk {
                            chunk_id: "content".into(),
                            content: serde_json::Value::String(
                                "one two three four five six seven eight".into(),
                            ),
                            kind: "text".into(),
                            fixed: false,
                            protection: "elastic".into(),
                            priority: 1.0,
                            required_terms: vec![],
                            dependency_group: None,
                            metadata: Default::default(),
                        }],
                        observed_demand_tokens: None,
                        metadata: Default::default(),
                    }],
                    request_id: Some("invariant".into()),
                })
                .unwrap();
            assert_eq!(prepared.input_budget_tokens, input_budget);
            assert!(prepared.prompt_tokens <= prepared.input_budget_tokens);
            assert!(
                prepared
                    .allocations
                    .iter()
                    .map(|allocation| allocation.allocated_tokens)
                    .sum::<i32>()
                    <= input_budget
            );
        }
    }
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
