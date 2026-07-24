use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::cell::Cell;
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::fmt;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

pub const CORE_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub struct CompressionStepSpec {
    pub algorithm_id: String,
    #[serde(default)]
    pub options: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleDefinition {
    pub module_id: String,
    pub floor_tokens: i32,
    pub target_tokens: i32,
    pub max_tokens: i32,
    #[serde(default)]
    pub order: i32,
    #[serde(default = "one_f64")]
    pub weight: f64,
    #[serde(default = "request_lifecycle")]
    pub lifecycle: String,
    #[serde(default = "weighted_allocation")]
    pub allocation: String,
    #[serde(default = "mixed")]
    pub protection: String,
    #[serde(default = "builtin_reclaim")]
    pub reclaim: String,
    #[serde(default = "text_render_target")]
    pub render_target: String,
    #[serde(default = "yes")]
    pub can_borrow: bool,
    #[serde(default = "yes")]
    pub can_lend: bool,
    #[serde(default)]
    pub reclaim_pipeline: Vec<CompressionStepSpec>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ArenaDefinition {
    pub arena_id: String,
    pub modules: Vec<ModuleDefinition>,
    #[serde(default = "v1")]
    pub schema_version: String,
    #[serde(default = "policy_v1")]
    pub policy_version: String,
    #[serde(default)]
    pub framework_reserve_tokens: i32,
    #[serde(default = "reject_admission")]
    pub admission_policy: String,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelProfile {
    pub model_profile_id: String,
    pub context_limit_tokens: i32,
    pub reserved_output_tokens: i32,
    #[serde(default = "tokenizer")]
    pub tokenizer_id: String,
    #[serde(default = "tokenizer_v1")]
    pub tokenizer_version: String,
    #[serde(default = "estimated_count_mode")]
    pub count_mode: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PromptChunk {
    pub chunk_id: String,
    pub content: Value,
    #[serde(default = "text_kind")]
    pub kind: String,
    #[serde(default)]
    pub fixed: bool,
    #[serde(default = "elastic")]
    pub protection: String,
    #[serde(default = "one_f64")]
    pub priority: f64,
    #[serde(default)]
    pub required_terms: Vec<String>,
    #[serde(default)]
    pub dependency_group: Option<String>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModuleContribution {
    pub module_id: String,
    #[serde(default)]
    pub chunks: Vec<PromptChunk>,
    #[serde(default)]
    pub observed_demand_tokens: Option<i32>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrepareRequest {
    #[serde(default = "v1")]
    pub schema_version: String,
    pub model: ModelProfile,
    #[serde(default)]
    pub contributions: Vec<ModuleContribution>,
    #[serde(default)]
    pub request_id: Option<String>,
}

/// Versioned, language-neutral input IR. `PrepareRequest` remains as the
/// source-compatible Rust name while every binding exchanges a ContextPlan.
pub type ContextPlan = PrepareRequest;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticRequest {
    pub semantic_request_id: String,
    pub module_id: String,
    pub algorithm_id: String,
    pub provider_id: String,
    pub source_text: String,
    pub target_tokens: i32,
    pub required_terms: Vec<String>,
    #[serde(default)]
    pub options: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SemanticResult {
    pub semantic_request_id: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrepareBeginOutcome {
    pub status: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prepared: Option<PreparedContext>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub semantic_requests: Vec<SemanticRequest>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ModuleAllocation {
    pub module_id: String,
    pub floor_tokens: i32,
    pub target_tokens: i32,
    pub max_tokens: i32,
    pub demanded_tokens: i32,
    pub allocated_tokens: i32,
    pub local_capacity_tokens: i32,
    pub borrowed_capacity_tokens: i32,
    pub lent_capacity_tokens: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Lease {
    pub lease_id: String,
    pub donor_module_id: String,
    pub borrower_module_id: String,
    pub granted_tokens: i32,
    pub currently_used_tokens: i32,
    pub reclaimable_tokens: i32,
    pub release_pipeline: Vec<String>,
    pub state: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleUsage {
    pub module_id: String,
    pub floor_tokens: i32,
    pub target_tokens: i32,
    pub max_tokens: i32,
    pub demanded_tokens: i32,
    pub allocated_tokens: i32,
    pub used_tokens: i32,
    pub fixed_tokens: i32,
    pub variable_tokens: i32,
    pub pinned_tokens: i32,
    pub elastic_tokens: i32,
    pub reclaimable_tokens: i32,
    pub minimum_retained_tokens: i32,
    pub local_capacity_tokens: i32,
    pub borrowed_capacity_tokens: i32,
    pub lent_capacity_tokens: i32,
    pub compressed_from_tokens: i32,
    pub compressed_to_tokens: i32,
    pub compression_ratio: f64,
    pub change_rate: f64,
    pub pressure: String,
    pub last_updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreparedChunk {
    pub chunk_id: String,
    pub kind: String,
    pub content: Value,
    pub fixed: bool,
    pub protection: String,
    pub priority: f64,
    pub required_terms: Vec<String>,
    pub dependency_group: Option<String>,
    pub metadata: BTreeMap<String, Value>,
    pub token_count: i32,
    pub compressed: bool,
    pub source_chunk_ids: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreparedModulePlan {
    pub module_id: String,
    pub render_target: String,
    pub allocation: ModuleAllocation,
    pub usage: ModuleUsage,
    pub chunks: Vec<PreparedChunk>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UsageCalibration {
    pub model_profile_id: String,
    pub tokenizer_id: String,
    pub tokenizer_version: String,
    pub sample_count: u64,
    pub ewma_ratio: f64,
    pub safety_multiplier: f64,
    pub last_estimated_tokens: i32,
    pub last_actual_tokens: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UsageObservation {
    pub request_id: String,
    pub actual_input_tokens: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceEvent {
    pub event_id: String,
    pub seq: u64,
    pub occurred_at: String,
    pub arena_id: String,
    pub instance_id: String,
    pub request_id: Option<String>,
    pub event_type: String,
    pub schema_version: String,
    pub layout_hash: String,
    pub policy_version: String,
    pub payload: BTreeMap<String, Value>,
    pub priority: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArenaSnapshot {
    pub schema_version: String,
    pub arena_id: String,
    pub instance_id: String,
    pub snapshot_seq: u64,
    pub captured_at: String,
    pub request_id: Option<String>,
    pub model_profile_id: String,
    pub tokenizer_id: String,
    pub tokenizer_version: String,
    pub token_count_mode: String,
    pub layout_hash: String,
    pub policy_version: String,
    pub context_limit_tokens: i32,
    pub reserved_output_tokens: i32,
    pub framework_reserve_tokens: i32,
    pub input_budget_tokens: i32,
    pub used_tokens: i32,
    pub slack_tokens: i32,
    pub utilization: f64,
    pub pressure: String,
    pub modules: Vec<ModuleUsage>,
    pub leases: Vec<Lease>,
    pub calibration: Option<UsageCalibration>,
    pub health: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreparedContextPlan {
    pub schema_version: String,
    pub core_version: String,
    pub arena_id: String,
    pub instance_id: String,
    pub request_id: String,
    pub layout_hash: String,
    pub policy_version: String,
    pub model_profile_id: String,
    pub tokenizer_id: String,
    pub tokenizer_version: String,
    pub token_count_mode: String,
    pub context_limit_tokens: i32,
    pub reserved_output_tokens: i32,
    pub framework_reserve_tokens: i32,
    pub rendered: String,
    pub prompt_tokens: i32,
    pub input_budget_tokens: i32,
    pub slack_tokens: i32,
    pub pressure: String,
    pub allocations: Vec<ModuleAllocation>,
    pub leases: Vec<Lease>,
    pub modules: Vec<ModuleUsage>,
    pub module_plans: Vec<PreparedModulePlan>,
    pub trace_events: Vec<TraceEvent>,
    pub snapshot: ArenaSnapshot,
    pub calibration: Option<UsageCalibration>,
}

/// Compatibility alias retained for 0.2 Rust callers.
pub type PreparedContext = PreparedContextPlan;

#[derive(Debug, Clone)]
pub struct ContextLeaseError {
    pub code: &'static str,
    pub message: String,
}

impl ContextLeaseError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl fmt::Display for ContextLeaseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for ContextLeaseError {}

#[derive(Debug, Clone)]
struct RecentUsage {
    model_profile_id: String,
    tokenizer_id: String,
    tokenizer_version: String,
    estimated_tokens: i32,
}

#[derive(Default)]
struct ArenaState {
    request_seq: u64,
    snapshot_seq: u64,
    event_seq: u64,
    previous_usage: HashMap<String, i32>,
    active_leases: HashMap<String, Lease>,
    calibrations: HashMap<String, UsageCalibration>,
    recent_usage: HashMap<String, RecentUsage>,
    recent_usage_order: VecDeque<String>,
    events: VecDeque<TraceEvent>,
    events_dropped: u64,
    latest_snapshot: Option<ArenaSnapshot>,
}

impl ArenaState {
    fn begin_transaction(&self) -> Self {
        Self {
            request_seq: self.request_seq,
            snapshot_seq: self.snapshot_seq,
            event_seq: self.event_seq,
            previous_usage: self.previous_usage.clone(),
            active_leases: self.active_leases.clone(),
            calibrations: self.calibrations.clone(),
            recent_usage: self.recent_usage.clone(),
            recent_usage_order: self.recent_usage_order.clone(),
            events: VecDeque::new(),
            events_dropped: self.events_dropped,
            latest_snapshot: self.latest_snapshot.clone(),
        }
    }

    fn commit_transaction(&mut self, mut transaction: Self) {
        self.request_seq = transaction.request_seq;
        self.snapshot_seq = transaction.snapshot_seq;
        self.event_seq = transaction.event_seq;
        self.previous_usage = transaction.previous_usage;
        self.active_leases = transaction.active_leases;
        self.calibrations = transaction.calibrations;
        self.recent_usage = transaction.recent_usage;
        self.recent_usage_order = transaction.recent_usage_order;
        self.events_dropped = transaction.events_dropped;
        for event in transaction.events.drain(..) {
            if self.events.len() == 10_000 {
                self.events.pop_front();
                self.events_dropped += 1;
            }
            self.events.push_back(event);
        }
        self.latest_snapshot = transaction.latest_snapshot;
        if let Some(snapshot) = self.latest_snapshot.as_mut() {
            snapshot
                .health
                .insert("events_dropped".into(), Value::from(self.events_dropped));
        }
    }
}

pub struct ContextLeaseArena {
    definition: ArenaDefinition,
    layout_hash: String,
    instance_id: String,
    order: Vec<usize>,
    state: Mutex<ArenaState>,
}

/// Host tokenizer interface used by Rust callers and the C ABI callback.
/// Implementations must be deterministic for the duration of one prepare.
pub trait TokenCounter: Send + Sync {
    fn count_text(&self, text: &str) -> i32;
}

struct CountContext<'a> {
    tokenizer_id: &'a str,
    external: Option<&'a dyn TokenCounter>,
    safety_multiplier: f64,
    failed: Cell<bool>,
}

impl CountContext<'_> {
    fn count_text(&self, text: &str) -> i32 {
        let raw = self
            .external
            .map(|counter| counter.count_text(text))
            .unwrap_or_else(|| estimate_text(text, self.tokenizer_id));
        if raw < 0 {
            self.failed.set(true);
            return 0;
        }
        if self.external.is_some() {
            raw
        } else {
            ((raw as f64) * self.safety_multiplier).ceil() as i32
        }
    }

    fn count_content(&self, value: &Value) -> i32 {
        match value {
            Value::String(text) => self.count_text(text),
            Value::Null => 0,
            value => self.count_text(&serde_json::to_string(value).unwrap_or_default()),
        }
    }

    fn ensure_valid(&self) -> Result<(), ContextLeaseError> {
        if self.failed.get() {
            Err(ContextLeaseError::new(
                "tokenizer_callback_failed",
                "host tokenizer callback returned an error",
            ))
        } else {
            Ok(())
        }
    }
}

impl ContextLeaseArena {
    pub fn new(definition: ArenaDefinition) -> Result<Self, ContextLeaseError> {
        validate_definition(&definition)?;
        // Hash the JSON value rather than the Rust struct directly.  serde_json's
        // map representation is key ordered, matching the Python canonical
        // `sort_keys=True` contract used by every binding fixture.
        let canonical_value = serde_json::to_value(&definition)
            .map_err(|e| ContextLeaseError::new("serialization_error", e.to_string()))?;
        let canonical = serde_json::to_vec(&canonical_value)
            .map_err(|e| ContextLeaseError::new("serialization_error", e.to_string()))?;
        let layout_hash = format!("{:x}", Sha256::digest(canonical))[..24].to_string();
        let mut order: Vec<usize> = (0..definition.modules.len()).collect();
        order.sort_by(|a, b| {
            let a = &definition.modules[*a];
            let b = &definition.modules[*b];
            (a.order, &a.module_id).cmp(&(b.order, &b.module_id))
        });
        Ok(Self {
            instance_id: format!(
                "{}-{}-{}",
                definition.arena_id,
                std::process::id(),
                unix_millis()
            ),
            definition,
            layout_hash,
            order,
            state: Mutex::new(ArenaState::default()),
        })
    }

    pub fn prepare(&self, request: PrepareRequest) -> Result<PreparedContext, ContextLeaseError> {
        self.prepare_with_counter_and_semantic_results(request, &[], None)
    }

    pub fn prepare_with_counter(
        &self,
        request: PrepareRequest,
        counter: &dyn TokenCounter,
    ) -> Result<PreparedContext, ContextLeaseError> {
        self.prepare_with_counter_and_semantic_results(request, &[], Some(counter))
    }

    pub fn prepare_begin(
        &self,
        request: PrepareRequest,
    ) -> Result<PrepareBeginOutcome, ContextLeaseError> {
        self.prepare_begin_with_optional_counter(request, None)
    }

    pub fn prepare_begin_with_counter(
        &self,
        request: PrepareRequest,
        counter: &dyn TokenCounter,
    ) -> Result<PrepareBeginOutcome, ContextLeaseError> {
        self.prepare_begin_with_optional_counter(request, Some(counter))
    }

    fn prepare_begin_with_optional_counter(
        &self,
        request: PrepareRequest,
        counter: Option<&dyn TokenCounter>,
    ) -> Result<PrepareBeginOutcome, ContextLeaseError> {
        let semantic_requests = self.plan_semantic_requests(&request, counter)?;
        if semantic_requests.is_empty() {
            return Ok(PrepareBeginOutcome {
                status: "ready".into(),
                prepared: Some(self.prepare_with_counter_and_semantic_results(
                    request,
                    &[],
                    counter,
                )?),
                semantic_requests: Vec::new(),
            });
        }
        Ok(PrepareBeginOutcome {
            status: "needs_semantic".into(),
            prepared: None,
            semantic_requests,
        })
    }

    pub fn prepare_commit(
        &self,
        request: PrepareRequest,
        results: Vec<SemanticResult>,
    ) -> Result<PreparedContext, ContextLeaseError> {
        self.prepare_commit_with_optional_counter(request, results, None)
    }

    pub fn prepare_commit_with_counter(
        &self,
        request: PrepareRequest,
        results: Vec<SemanticResult>,
        counter: &dyn TokenCounter,
    ) -> Result<PreparedContext, ContextLeaseError> {
        self.prepare_commit_with_optional_counter(request, results, Some(counter))
    }

    fn prepare_commit_with_optional_counter(
        &self,
        request: PrepareRequest,
        results: Vec<SemanticResult>,
        counter: Option<&dyn TokenCounter>,
    ) -> Result<PreparedContext, ContextLeaseError> {
        let expected = self.plan_semantic_requests(&request, counter)?;
        let expected_ids: BTreeSet<&str> = expected
            .iter()
            .map(|item| item.semantic_request_id.as_str())
            .collect();
        let mut seen = BTreeSet::new();
        for result in &results {
            if !seen.insert(result.semantic_request_id.as_str()) {
                return Err(ContextLeaseError::new(
                    "semantic_result_duplicate",
                    format!("duplicate semantic result {}", result.semantic_request_id),
                ));
            }
            if !expected_ids.contains(result.semantic_request_id.as_str()) {
                return Err(ContextLeaseError::new(
                    "semantic_result_unexpected",
                    format!("unexpected semantic result {}", result.semantic_request_id),
                ));
            }
        }
        self.prepare_with_counter_and_semantic_results(request, &results, counter)
    }

    fn prepare_with_counter_and_semantic_results(
        &self,
        request: PrepareRequest,
        results: &[SemanticResult],
        external_counter: Option<&dyn TokenCounter>,
    ) -> Result<PreparedContext, ContextLeaseError> {
        let semantic_results: HashMap<&str, &str> = results
            .iter()
            .map(|result| (result.semantic_request_id.as_str(), result.content.as_str()))
            .collect();
        validate_plan(&request)?;
        validate_model(&request.model)?;
        if request.model.count_mode == "exact" && external_counter.is_none() {
            return Err(ContextLeaseError::new(
                "tokenizer_unavailable",
                "exact count mode requires a host token counter",
            ));
        }
        let calibration_key = calibration_key(&request.model);
        let safety_multiplier = {
            let state = self.state.lock().map_err(|_| {
                ContextLeaseError::new("arena_poisoned", "arena state lock poisoned")
            })?;
            state
                .calibrations
                .get(&calibration_key)
                .map(|item| item.safety_multiplier)
                .unwrap_or(1.0)
        };
        let counts = CountContext {
            tokenizer_id: request.model.tokenizer_id.as_str(),
            external: external_counter,
            safety_multiplier,
            failed: Cell::new(false),
        };
        let input_budget =
            request.model.context_limit_tokens - request.model.reserved_output_tokens;
        let contributions = validate_contributions(&self.definition, request.contributions)?;
        let render_overhead = render_separator_tokens(&self.definition, &contributions, &counts);
        let allocation_input_budget = input_budget - render_overhead;
        validate_model_budget(&self.definition, allocation_input_budget)?;
        let demands: HashMap<String, i32> = self
            .definition
            .modules
            .iter()
            .map(|m| {
                let contribution = contributions.get(&m.module_id);
                let calculated = contribution
                    .map(|c| {
                        c.chunks
                            .iter()
                            .map(|x| counts.count_content(&x.content))
                            .sum()
                    })
                    .unwrap_or(0);
                (
                    m.module_id.clone(),
                    contribution
                        .and_then(|c| c.observed_demand_tokens)
                        .unwrap_or(calculated)
                        .max(0),
                )
            })
            .collect();
        let (allocations, leases) = allocate(
            &self.definition,
            &self.layout_hash,
            &demands,
            allocation_input_budget,
        )?;
        let allocation_by_id: HashMap<String, ModuleAllocation> = allocations
            .iter()
            .cloned()
            .map(|a| (a.module_id.clone(), a))
            .collect();
        let mut committed_state = self
            .state
            .lock()
            .map_err(|_| ContextLeaseError::new("arena_poisoned", "arena state lock poisoned"))?;
        let mut state = committed_state.begin_transaction();
        state.request_seq += 1;
        let request_id = request
            .request_id
            .filter(|x| !x.trim().is_empty())
            .unwrap_or_else(|| format!("{}:{}", self.definition.arena_id, state.request_seq));
        let now = timestamp_now();
        let mut trace_events = Vec::new();
        trace_events.push(self.push_event_locked(
            &mut state,
            Some(request_id.clone()),
            "request.started",
            BTreeMap::from([
                (
                    "model_profile_id".into(),
                    Value::String(request.model.model_profile_id.clone()),
                ),
                (
                    "token_count_mode".into(),
                    Value::String(request.model.count_mode.clone()),
                ),
            ]),
            "state",
        ));
        let next_leases: HashMap<String, Lease> = leases
            .iter()
            .cloned()
            .map(|lease| (lease.lease_id.clone(), lease))
            .collect();
        let previous_leases: Vec<Lease> = state.active_leases.values().cloned().collect();
        for previous in previous_leases {
            let current = next_leases.get(&previous.lease_id);
            let reclaimed =
                previous.granted_tokens - current.map(|lease| lease.granted_tokens).unwrap_or(0);
            if reclaimed > 0 {
                trace_events.push(self.push_event_locked(
                    &mut state,
                    Some(request_id.clone()),
                    "lease.reclaimed",
                    BTreeMap::from([
                        ("lease_id".into(), Value::String(previous.lease_id.clone())),
                        ("reclaimed_tokens".into(), Value::from(reclaimed)),
                        (
                            "borrower_module_id".into(),
                            Value::String(previous.borrower_module_id.clone()),
                        ),
                    ]),
                    "state",
                ));
            }
        }
        for lease in &leases {
            let granted = lease.granted_tokens
                - state
                    .active_leases
                    .get(&lease.lease_id)
                    .map(|previous| previous.granted_tokens)
                    .unwrap_or(0);
            if granted > 0 {
                trace_events.push(self.push_event_locked(
                    &mut state,
                    Some(request_id.clone()),
                    "lease.granted",
                    BTreeMap::from([
                        ("lease_id".into(), Value::String(lease.lease_id.clone())),
                        ("granted_tokens".into(), Value::from(granted)),
                        (
                            "borrower_module_id".into(),
                            Value::String(lease.borrower_module_id.clone()),
                        ),
                    ]),
                    "state",
                ));
            }
        }
        let mut final_chunks: HashMap<String, Vec<PromptChunk>> = HashMap::new();
        let mut module_usage = Vec::new();
        for index in &self.order {
            let module = &self.definition.modules[*index];
            let allocation = &allocation_by_id[&module.module_id];
            let chunks = contributions
                .get(&module.module_id)
                .map(|c| c.chunks.clone())
                .unwrap_or_default();
            let before: i32 = chunks
                .iter()
                .map(|c| counts.count_content(&c.content))
                .sum();
            let (chunks, after) = if before > allocation.allocated_tokens {
                compress_module(
                    module,
                    chunks,
                    allocation.allocated_tokens,
                    &semantic_results,
                    &counts,
                )?
            } else {
                (chunks, before)
            };
            if after < before {
                trace_events.push(self.push_event_locked(
                    &mut state,
                    Some(request_id.clone()),
                    "chunk.compressed",
                    BTreeMap::from([
                        ("module_id".into(), Value::String(module.module_id.clone())),
                        ("before_tokens".into(), Value::from(before)),
                        ("after_tokens".into(), Value::from(after)),
                    ]),
                    "state",
                ));
            }
            let fixed_tokens = chunks
                .iter()
                .filter(|c| c.fixed)
                .map(|c| counts.count_content(&c.content))
                .sum();
            let pinned_tokens = chunks
                .iter()
                .filter(|c| module.protection == "pinned" || c.protection == "pinned")
                .map(|c| counts.count_content(&c.content))
                .sum();
            let previous = state
                .previous_usage
                .insert(module.module_id.clone(), after)
                .unwrap_or(after);
            module_usage.push(ModuleUsage {
                module_id: module.module_id.clone(),
                floor_tokens: allocation.floor_tokens,
                target_tokens: allocation.target_tokens,
                max_tokens: allocation.max_tokens,
                demanded_tokens: allocation.demanded_tokens,
                allocated_tokens: allocation.allocated_tokens,
                used_tokens: after,
                fixed_tokens,
                variable_tokens: (after - fixed_tokens).max(0),
                pinned_tokens,
                elastic_tokens: (after - pinned_tokens).max(0),
                reclaimable_tokens: (after - pinned_tokens).max(0),
                minimum_retained_tokens: pinned_tokens,
                local_capacity_tokens: allocation.local_capacity_tokens,
                borrowed_capacity_tokens: allocation.borrowed_capacity_tokens,
                lent_capacity_tokens: allocation.lent_capacity_tokens,
                compressed_from_tokens: before,
                compressed_to_tokens: after,
                compression_ratio: if before == 0 {
                    1.0
                } else {
                    after as f64 / before as f64
                },
                change_rate: (after - previous) as f64 / previous.max(1) as f64,
                pressure: pressure(after, allocation.allocated_tokens),
                last_updated_at: now.clone(),
            });
            final_chunks.insert(module.module_id.clone(), chunks);
        }
        state.active_leases = next_leases;
        let rendered = self
            .order
            .iter()
            .filter_map(|index| {
                let id = &self.definition.modules[*index].module_id;
                let text = final_chunks
                    .get(id)
                    .into_iter()
                    .flatten()
                    .map(|c| render(&c.content))
                    .filter(|x| !x.is_empty())
                    .collect::<Vec<_>>()
                    .join("\n\n");
                (!text.is_empty()).then_some(text)
            })
            .collect::<Vec<_>>()
            .join("\n\n");
        let prompt_tokens = counts.count_text(&rendered);
        let usable = input_budget - self.definition.framework_reserve_tokens;
        if prompt_tokens > usable {
            return Err(ContextLeaseError::new(
                "admission_error",
                "rendered context exceeds usable budget",
            ));
        }
        let module_plans: Vec<PreparedModulePlan> = self
            .order
            .iter()
            .enumerate()
            .map(|(usage_index, definition_index)| {
                let module = &self.definition.modules[*definition_index];
                let chunks = final_chunks
                    .get(&module.module_id)
                    .cloned()
                    .unwrap_or_default()
                    .into_iter()
                    .map(|chunk| {
                        let compressed =
                            chunk.chunk_id == format!("{}:compressed", module.module_id);
                        let source_chunk_ids = chunk
                            .metadata
                            .get("source_chunk_ids")
                            .and_then(Value::as_array)
                            .map(|values| {
                                values
                                    .iter()
                                    .filter_map(Value::as_str)
                                    .map(str::to_string)
                                    .collect()
                            })
                            .unwrap_or_else(|| vec![chunk.chunk_id.clone()]);
                        PreparedChunk {
                            token_count: counts.count_content(&chunk.content),
                            chunk_id: chunk.chunk_id,
                            kind: chunk.kind,
                            content: chunk.content,
                            fixed: chunk.fixed,
                            protection: chunk.protection,
                            priority: chunk.priority,
                            required_terms: chunk.required_terms,
                            dependency_group: chunk.dependency_group,
                            metadata: chunk.metadata,
                            compressed,
                            source_chunk_ids,
                        }
                    })
                    .collect();
                PreparedModulePlan {
                    module_id: module.module_id.clone(),
                    render_target: module.render_target.clone(),
                    allocation: allocation_by_id[&module.module_id].clone(),
                    usage: module_usage[usage_index].clone(),
                    chunks,
                }
            })
            .collect();
        trace_events.push(self.push_event_locked(
            &mut state,
            Some(request_id.clone()),
            "request.prepared",
            BTreeMap::from([
                ("prompt_tokens".into(), Value::from(prompt_tokens)),
                ("input_budget_tokens".into(), Value::from(usable)),
            ]),
            "state",
        ));
        state.snapshot_seq += 1;
        let calibration = state.calibrations.get(&calibration_key).cloned();
        let mut health = BTreeMap::new();
        health.insert("events_dropped".into(), Value::from(state.events_dropped));
        health.insert("core_version".into(), Value::String(CORE_VERSION.into()));
        let snapshot = ArenaSnapshot {
            schema_version: "1.0".into(),
            arena_id: self.definition.arena_id.clone(),
            instance_id: self.instance_id.clone(),
            snapshot_seq: state.snapshot_seq,
            captured_at: timestamp_now(),
            request_id: Some(request_id.clone()),
            model_profile_id: request.model.model_profile_id.clone(),
            tokenizer_id: request.model.tokenizer_id.clone(),
            tokenizer_version: request.model.tokenizer_version.clone(),
            token_count_mode: request.model.count_mode.clone(),
            layout_hash: self.layout_hash.clone(),
            policy_version: self.definition.policy_version.clone(),
            context_limit_tokens: request.model.context_limit_tokens,
            reserved_output_tokens: request.model.reserved_output_tokens,
            framework_reserve_tokens: self.definition.framework_reserve_tokens,
            input_budget_tokens: usable,
            used_tokens: prompt_tokens,
            slack_tokens: usable - prompt_tokens,
            utilization: prompt_tokens as f64 / usable.max(1) as f64,
            pressure: pressure(prompt_tokens, usable),
            modules: module_usage.clone(),
            leases: leases.clone(),
            calibration: calibration.clone(),
            health,
        };
        state.latest_snapshot = Some(snapshot.clone());
        trace_events.push(self.push_event_locked(
            &mut state,
            Some(request_id.clone()),
            "snapshot.published",
            BTreeMap::from([("snapshot_seq".into(), Value::from(snapshot.snapshot_seq))]),
            "gauge",
        ));
        state.recent_usage.insert(
            request_id.clone(),
            RecentUsage {
                model_profile_id: request.model.model_profile_id.clone(),
                tokenizer_id: request.model.tokenizer_id.clone(),
                tokenizer_version: request.model.tokenizer_version.clone(),
                estimated_tokens: prompt_tokens,
            },
        );
        state
            .recent_usage_order
            .retain(|candidate| candidate != &request_id);
        state.recent_usage_order.push_back(request_id.clone());
        while state.recent_usage_order.len() > 2_048 {
            if let Some(expired) = state.recent_usage_order.pop_front() {
                state.recent_usage.remove(&expired);
            }
        }
        counts.ensure_valid()?;
        let prepared = PreparedContext {
            schema_version: "1.0".into(),
            core_version: CORE_VERSION.into(),
            arena_id: self.definition.arena_id.clone(),
            instance_id: self.instance_id.clone(),
            request_id,
            layout_hash: self.layout_hash.clone(),
            policy_version: self.definition.policy_version.clone(),
            model_profile_id: request.model.model_profile_id,
            tokenizer_id: request.model.tokenizer_id,
            tokenizer_version: request.model.tokenizer_version,
            token_count_mode: request.model.count_mode,
            context_limit_tokens: request.model.context_limit_tokens,
            reserved_output_tokens: request.model.reserved_output_tokens,
            framework_reserve_tokens: self.definition.framework_reserve_tokens,
            rendered,
            prompt_tokens,
            input_budget_tokens: usable,
            slack_tokens: usable - prompt_tokens,
            pressure: pressure(prompt_tokens, usable),
            allocations,
            leases,
            modules: module_usage,
            module_plans,
            trace_events,
            snapshot,
            calibration,
        };
        committed_state.commit_transaction(state);
        Ok(prepared)
    }

    pub fn snapshot(&self) -> Result<Option<ArenaSnapshot>, ContextLeaseError> {
        let state = self
            .state
            .lock()
            .map_err(|_| ContextLeaseError::new("arena_poisoned", "arena state lock poisoned"))?;
        Ok(state.latest_snapshot.clone())
    }

    pub fn events_after(
        &self,
        after_seq: u64,
        limit: usize,
    ) -> Result<Vec<TraceEvent>, ContextLeaseError> {
        let state = self
            .state
            .lock()
            .map_err(|_| ContextLeaseError::new("arena_poisoned", "arena state lock poisoned"))?;
        Ok(state
            .events
            .iter()
            .filter(|event| event.seq > after_seq)
            .take(limit.clamp(1, 10_000))
            .cloned()
            .collect())
    }

    pub fn record_usage(
        &self,
        observation: UsageObservation,
    ) -> Result<UsageCalibration, ContextLeaseError> {
        if observation.request_id.trim().is_empty() || observation.actual_input_tokens < 0 {
            return Err(ContextLeaseError::new(
                "configuration_error",
                "usage observation requires request_id and non-negative actual_input_tokens",
            ));
        }
        let mut state = self
            .state
            .lock()
            .map_err(|_| ContextLeaseError::new("arena_poisoned", "arena state lock poisoned"))?;
        let recent = state
            .recent_usage
            .remove(&observation.request_id)
            .ok_or_else(|| {
                ContextLeaseError::new(
                    "usage_observation_unknown",
                    format!("unknown request_id {}", observation.request_id),
                )
            })?;
        state
            .recent_usage_order
            .retain(|candidate| candidate != &observation.request_id);
        let key = calibration_key_parts(
            &recent.model_profile_id,
            &recent.tokenizer_id,
            &recent.tokenizer_version,
        );
        let ratio = if recent.estimated_tokens <= 0 {
            1.0
        } else {
            observation.actual_input_tokens as f64 / recent.estimated_tokens as f64
        };
        let entry = state.calibrations.entry(key).or_insert(UsageCalibration {
            model_profile_id: recent.model_profile_id,
            tokenizer_id: recent.tokenizer_id,
            tokenizer_version: recent.tokenizer_version,
            sample_count: 0,
            ewma_ratio: 1.0,
            safety_multiplier: 1.0,
            last_estimated_tokens: 0,
            last_actual_tokens: 0,
        });
        entry.sample_count += 1;
        entry.ewma_ratio = if entry.sample_count == 1 {
            ratio
        } else {
            0.2 * ratio + 0.8 * entry.ewma_ratio
        };
        entry.safety_multiplier = entry.ewma_ratio.max(1.0);
        entry.last_estimated_tokens = recent.estimated_tokens;
        entry.last_actual_tokens = observation.actual_input_tokens;
        let calibration = entry.clone();
        let event = self.push_event_locked(
            &mut state,
            Some(observation.request_id),
            "usage.calibrated",
            BTreeMap::from([
                ("sample_count".into(), Value::from(calibration.sample_count)),
                (
                    "estimated_input_tokens".into(),
                    Value::from(calibration.last_estimated_tokens),
                ),
                (
                    "actual_input_tokens".into(),
                    Value::from(calibration.last_actual_tokens),
                ),
                (
                    "safety_multiplier".into(),
                    Value::from(calibration.safety_multiplier),
                ),
            ]),
            "state",
        );
        let events_dropped = state.events_dropped;
        if let Some(snapshot) = state.latest_snapshot.as_mut() {
            snapshot.calibration = Some(calibration.clone());
            snapshot
                .health
                .insert("last_calibration_event_seq".into(), Value::from(event.seq));
            snapshot
                .health
                .insert("events_dropped".into(), Value::from(events_dropped));
        }
        Ok(calibration)
    }

    fn push_event_locked(
        &self,
        state: &mut ArenaState,
        request_id: Option<String>,
        event_type: &str,
        payload: BTreeMap<String, Value>,
        priority: &str,
    ) -> TraceEvent {
        state.event_seq += 1;
        let event = TraceEvent {
            event_id: format!("{}:{}", self.instance_id, state.event_seq),
            seq: state.event_seq,
            occurred_at: timestamp_now(),
            arena_id: self.definition.arena_id.clone(),
            instance_id: self.instance_id.clone(),
            request_id,
            event_type: event_type.into(),
            schema_version: "1.0".into(),
            layout_hash: self.layout_hash.clone(),
            policy_version: self.definition.policy_version.clone(),
            payload,
            priority: priority.into(),
        };
        if state.events.len() == 10_000 {
            state.events.pop_front();
            state.events_dropped += 1;
        }
        state.events.push_back(event.clone());
        event
    }

    fn plan_semantic_requests(
        &self,
        request: &PrepareRequest,
        external_counter: Option<&dyn TokenCounter>,
    ) -> Result<Vec<SemanticRequest>, ContextLeaseError> {
        validate_plan(request)?;
        validate_model(&request.model)?;
        if request.model.count_mode == "exact" && external_counter.is_none() {
            return Err(ContextLeaseError::new(
                "tokenizer_unavailable",
                "exact count mode requires a host token counter",
            ));
        }
        let calibration = {
            let state = self.state.lock().map_err(|_| {
                ContextLeaseError::new("arena_poisoned", "arena state lock poisoned")
            })?;
            state
                .calibrations
                .get(&calibration_key(&request.model))
                .map(|value| value.safety_multiplier)
                .unwrap_or(1.0)
        };
        let counts = CountContext {
            tokenizer_id: request.model.tokenizer_id.as_str(),
            external: external_counter,
            safety_multiplier: calibration,
            failed: Cell::new(false),
        };
        let input_budget =
            request.model.context_limit_tokens - request.model.reserved_output_tokens;
        let contributions =
            validate_contributions(&self.definition, request.contributions.clone())?;
        let render_overhead = render_separator_tokens(&self.definition, &contributions, &counts);
        let allocation_input_budget = input_budget - render_overhead;
        validate_model_budget(&self.definition, allocation_input_budget)?;
        let demands: HashMap<String, i32> = self
            .definition
            .modules
            .iter()
            .map(|module| {
                let contribution = contributions.get(&module.module_id);
                let calculated = contribution
                    .map(|item| {
                        item.chunks
                            .iter()
                            .map(|chunk| counts.count_content(&chunk.content))
                            .sum()
                    })
                    .unwrap_or(0);
                (
                    module.module_id.clone(),
                    contribution
                        .and_then(|item| item.observed_demand_tokens)
                        .unwrap_or(calculated)
                        .max(0),
                )
            })
            .collect();
        let (allocations, _) = allocate(
            &self.definition,
            &self.layout_hash,
            &demands,
            allocation_input_budget,
        )?;
        let allocation_by_id: HashMap<&str, i32> = allocations
            .iter()
            .map(|item| (item.module_id.as_str(), item.allocated_tokens))
            .collect();
        let mut requests = Vec::new();
        for index in &self.order {
            let module = &self.definition.modules[*index];
            let chunks = contributions
                .get(&module.module_id)
                .map(|item| item.chunks.clone())
                .unwrap_or_default();
            let before: i32 = chunks
                .iter()
                .map(|chunk| counts.count_content(&chunk.content))
                .sum();
            let allocation = allocation_by_id[module.module_id.as_str()];
            if before > allocation {
                requests.extend(collect_semantic_requests(
                    module, chunks, allocation, &counts,
                )?);
            }
        }
        counts.ensure_valid()?;
        Ok(requests)
    }
}

fn render_separator_tokens(
    definition: &ArenaDefinition,
    contributions: &HashMap<String, ModuleContribution>,
    counts: &CountContext<'_>,
) -> i32 {
    let rendered_module_count = definition
        .modules
        .iter()
        .filter(|module| {
            contributions
                .get(&module.module_id)
                .map(|contribution| {
                    contribution
                        .chunks
                        .iter()
                        .any(|chunk| !render(&chunk.content).is_empty())
                })
                .unwrap_or(false)
        })
        .count();
    if rendered_module_count <= 1 {
        return 0;
    }
    counts.count_text(&"\n\n".repeat(rendered_module_count - 1))
}

fn allocate(
    definition: &ArenaDefinition,
    layout_hash: &str,
    demands: &HashMap<String, i32>,
    input_budget: i32,
) -> Result<(Vec<ModuleAllocation>, Vec<Lease>), ContextLeaseError> {
    let available = input_budget - definition.framework_reserve_tokens;
    let mut current: HashMap<String, i32> = definition
        .modules
        .iter()
        .map(|m| {
            (
                m.module_id.clone(),
                m.floor_tokens.min(*demands.get(&m.module_id).unwrap_or(&0)),
            )
        })
        .collect();
    let mut remaining = available - current.values().sum::<i32>();
    if remaining < 0 {
        return Err(ContextLeaseError::new(
            "layout_validation_error",
            "module floors exceed budget",
        ));
    }
    let caps: HashMap<String, i32> = definition
        .modules
        .iter()
        .map(|m| {
            (
                m.module_id.clone(),
                m.target_tokens
                    .min(*demands.get(&m.module_id).unwrap_or(&0)),
            )
        })
        .collect();
    remaining = weighted_fill(&mut current, &caps, definition, remaining);
    let mut donors: Vec<(String, i32)> = definition
        .modules
        .iter()
        .filter(|m| m.can_lend)
        .map(|m| {
            (
                m.module_id.clone(),
                (m.target_tokens - current[&m.module_id]).max(0),
            )
        })
        .filter(|(_, amount)| *amount > 0)
        .collect();
    donors.sort_by(|a, b| a.0.cmp(&b.0));
    let donor_total: i32 = donors.iter().map(|(_, n)| *n).sum();
    let mut shared_slack = (remaining - donor_total).max(0);
    let mut borrowed: HashMap<String, i32> = definition
        .modules
        .iter()
        .map(|m| (m.module_id.clone(), 0))
        .collect();
    let mut lent = borrowed.clone();
    let mut leases = Vec::new();
    let mut borrowers: Vec<&ModuleDefinition> = definition
        .modules
        .iter()
        .filter(|m| {
            m.can_borrow
                && demands.get(&m.module_id).copied().unwrap_or(0) > m.target_tokens
                && current[&m.module_id] < m.max_tokens
        })
        .collect();
    borrowers.sort_by(|a, b| {
        b.weight
            .partial_cmp(&a.weight)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.order.cmp(&b.order))
            .then(a.module_id.cmp(&b.module_id))
    });
    for borrower in borrowers {
        let mut need =
            demands[&borrower.module_id].min(borrower.max_tokens) - current[&borrower.module_id];
        for (donor_id, donor_available) in &mut donors {
            if need <= 0 || remaining <= 0 {
                break;
            }
            if donor_id == &borrower.module_id || *donor_available <= 0 {
                continue;
            }
            let grant = need.min(*donor_available).min(remaining);
            *donor_available -= grant;
            need -= grant;
            remaining -= grant;
            *current.get_mut(&borrower.module_id).unwrap() += grant;
            *borrowed.get_mut(&borrower.module_id).unwrap() += grant;
            *lent.get_mut(donor_id).unwrap() += grant;
            leases.push(lease(layout_hash, donor_id, borrower, grant));
        }
        if need > 0 && shared_slack > 0 && remaining > 0 {
            let grant = need.min(shared_slack).min(remaining);
            shared_slack -= grant;
            remaining -= grant;
            *current.get_mut(&borrower.module_id).unwrap() += grant;
            *borrowed.get_mut(&borrower.module_id).unwrap() += grant;
            leases.push(lease(layout_hash, "__arena_slack__", borrower, grant));
        }
    }
    let mut modules: Vec<&ModuleDefinition> = definition.modules.iter().collect();
    modules.sort_by(|a, b| (a.order, &a.module_id).cmp(&(b.order, &b.module_id)));
    let allocations = modules
        .into_iter()
        .map(|m| ModuleAllocation {
            module_id: m.module_id.clone(),
            floor_tokens: m.floor_tokens,
            target_tokens: m.target_tokens,
            max_tokens: m.max_tokens,
            demanded_tokens: demands[&m.module_id],
            allocated_tokens: current[&m.module_id],
            local_capacity_tokens: (current[&m.module_id] - borrowed[&m.module_id]).max(0),
            borrowed_capacity_tokens: borrowed[&m.module_id],
            lent_capacity_tokens: lent[&m.module_id],
        })
        .collect();
    Ok((allocations, leases))
}

fn weighted_fill(
    current: &mut HashMap<String, i32>,
    caps: &HashMap<String, i32>,
    definition: &ArenaDefinition,
    mut remaining: i32,
) -> i32 {
    let weights: HashMap<&str, f64> = definition
        .modules
        .iter()
        .map(|m| (m.module_id.as_str(), m.weight))
        .collect();
    let mut active: BTreeSet<String> = caps
        .iter()
        .filter(|(id, cap)| current[*id] < **cap)
        .map(|(id, _)| id.clone())
        .collect();
    while remaining > 0 && !active.is_empty() {
        let total: f64 = active.iter().map(|id| weights[id.as_str()]).sum();
        let round = remaining;
        let mut progressed = 0;
        for id in active.iter().cloned().collect::<Vec<_>>() {
            let capacity = caps[&id] - current[&id];
            let share = ((round as f64 * weights[id.as_str()] / total) as i32).max(1);
            let grant = capacity.min(share).min(remaining);
            *current.get_mut(&id).unwrap() += grant;
            remaining -= grant;
            progressed += grant;
            if remaining == 0 {
                break;
            }
        }
        active.retain(|id| current[id] < caps[id]);
        if progressed == 0 {
            break;
        }
    }
    remaining
}

fn lease(hash: &str, donor: &str, borrower: &ModuleDefinition, grant: i32) -> Lease {
    Lease {
        lease_id: format!("{hash}:{donor}:{}", borrower.module_id),
        donor_module_id: donor.into(),
        borrower_module_id: borrower.module_id.clone(),
        granted_tokens: grant,
        currently_used_tokens: grant,
        reclaimable_tokens: grant,
        release_pipeline: borrower
            .reclaim_pipeline
            .iter()
            .map(|s| s.algorithm_id.clone())
            .collect(),
        state: "active".into(),
    }
}

fn collect_semantic_requests(
    module: &ModuleDefinition,
    chunks: Vec<PromptChunk>,
    allocation: i32,
    counts: &CountContext<'_>,
) -> Result<Vec<SemanticRequest>, ContextLeaseError> {
    let (protected, elastic): (Vec<_>, Vec<_>) = chunks.into_iter().partition(|chunk| {
        chunk.fixed || module.protection == "pinned" || chunk.protection == "pinned"
    });
    let protected_tokens: i32 = protected
        .iter()
        .map(|chunk| counts.count_content(&chunk.content))
        .sum();
    if protected_tokens > allocation {
        return Err(ContextLeaseError::new(
            "admission_error",
            format!("{} protected content exceeds allocation", module.module_id),
        ));
    }
    if elastic.is_empty() {
        return Ok(Vec::new());
    }
    let target = allocation - protected_tokens;
    let required: BTreeSet<String> = elastic
        .iter()
        .flat_map(|chunk| chunk.required_terms.iter().cloned())
        .collect();
    let mut text = elastic
        .iter()
        .map(|chunk| render(&chunk.content))
        .collect::<Vec<_>>()
        .join("\n\n");
    for step in &module.reclaim_pipeline {
        if counts.count_text(&text) <= target {
            break;
        }
        if is_semantic_algorithm(&step.algorithm_id) {
            return semantic_requests_for_step(module, step, &text, target, &required);
        }
        let candidate = compress_text(&step.algorithm_id, &text, target, counts);
        if counts.count_text(&candidate) <= counts.count_text(&text)
            && required.iter().all(|term| candidate.contains(term))
        {
            text = candidate;
        }
    }
    Ok(Vec::new())
}

fn semantic_requests_for_step(
    module: &ModuleDefinition,
    step: &CompressionStepSpec,
    source_text: &str,
    target_tokens: i32,
    required_terms: &BTreeSet<String>,
) -> Result<Vec<SemanticRequest>, ContextLeaseError> {
    let providers: Vec<String> = if step.algorithm_id == "builtin.semantic.portfolio.v1" {
        step.options
            .get("providers")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::trim)
                    .filter(|item| !item.is_empty())
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default()
    } else {
        step.options
            .get("provider")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|item| !item.is_empty())
            .map(|item| vec![item.to_string()])
            .unwrap_or_default()
    };
    if providers.is_empty() {
        return Err(ContextLeaseError::new(
            "configuration_error",
            format!("{} requires configured provider ids", step.algorithm_id),
        ));
    }
    let required_terms: Vec<String> = required_terms.iter().cloned().collect();
    Ok(providers
        .into_iter()
        .map(|provider_id| {
            let fingerprint = format!(
                "{}\0{}\0{}\0{}\0{}\0{}",
                module.module_id,
                step.algorithm_id,
                provider_id,
                target_tokens,
                required_terms.join("\0"),
                source_text
            );
            let semantic_request_id = format!(
                "sem_{}",
                &format!("{:x}", Sha256::digest(fingerprint.as_bytes()))[..24]
            );
            SemanticRequest {
                semantic_request_id,
                module_id: module.module_id.clone(),
                algorithm_id: step.algorithm_id.clone(),
                provider_id,
                source_text: source_text.to_string(),
                target_tokens,
                required_terms: required_terms.clone(),
                options: step.options.clone(),
            }
        })
        .collect())
}

fn is_semantic_algorithm(id: &str) -> bool {
    id == "builtin.semantic.summary.v1" || id == "builtin.semantic.portfolio.v1"
}

fn compress_module(
    module: &ModuleDefinition,
    chunks: Vec<PromptChunk>,
    allocation: i32,
    semantic_results: &HashMap<&str, &str>,
    counts: &CountContext<'_>,
) -> Result<(Vec<PromptChunk>, i32), ContextLeaseError> {
    let (mut pinned, elastic): (Vec<_>, Vec<_>) = chunks
        .into_iter()
        .partition(|c| c.fixed || module.protection == "pinned" || c.protection == "pinned");
    let pinned_tokens: i32 = pinned
        .iter()
        .map(|c| counts.count_content(&c.content))
        .sum();
    if pinned_tokens > allocation {
        return Err(ContextLeaseError::new(
            "admission_error",
            format!("{} pinned content exceeds allocation", module.module_id),
        ));
    }
    if elastic.is_empty() {
        return Err(ContextLeaseError::new(
            "admission_error",
            format!("{} has no elastic content", module.module_id),
        ));
    }
    let target = allocation - pinned_tokens;
    let required: BTreeSet<String> = elastic
        .iter()
        .flat_map(|c| c.required_terms.iter().cloned())
        .collect();
    let mut text = elastic
        .iter()
        .map(|c| render(&c.content))
        .collect::<Vec<_>>()
        .join("\n\n");
    for step in &module.reclaim_pipeline {
        if counts.count_text(&text) <= target {
            break;
        }
        if is_semantic_algorithm(&step.algorithm_id) {
            let requests = semantic_requests_for_step(module, step, &text, target, &required)?;
            let mut candidates: Vec<&str> = requests
                .iter()
                .filter_map(|request| {
                    semantic_results
                        .get(request.semantic_request_id.as_str())
                        .copied()
                })
                .filter(|candidate| {
                    !candidate.trim().is_empty()
                        && counts.count_text(candidate) <= counts.count_text(&text)
                        && required.iter().all(|term| candidate.contains(term))
                })
                .collect();
            candidates.sort_by_key(|candidate| counts.count_text(candidate));
            let candidate = candidates.first().copied().ok_or_else(|| {
                ContextLeaseError::new(
                    "semantic_result_missing_or_invalid",
                    format!(
                        "{} requires a valid semantic result for {}",
                        module.module_id, step.algorithm_id
                    ),
                )
            })?;
            text = candidate.to_string();
        } else {
            let candidate = compress_text(&step.algorithm_id, &text, target, counts);
            if counts.count_text(&candidate) <= counts.count_text(&text)
                && required.iter().all(|term| candidate.contains(term))
            {
                text = candidate;
            }
        }
    }
    let after = counts.count_text(&text);
    if after > target {
        return Err(ContextLeaseError::new(
            "admission_error",
            format!("{} reclaim target unmet", module.module_id),
        ));
    }
    let source_chunk_ids: Vec<Value> = elastic
        .iter()
        .map(|chunk| Value::String(chunk.chunk_id.clone()))
        .collect();
    let mut metadata = BTreeMap::new();
    metadata.insert("source_chunk_ids".into(), Value::Array(source_chunk_ids));
    metadata.insert(
        "compression_pipeline".into(),
        Value::Array(
            module
                .reclaim_pipeline
                .iter()
                .map(|step| Value::String(step.algorithm_id.clone()))
                .collect(),
        ),
    );
    pinned.push(PromptChunk {
        chunk_id: format!("{}:compressed", module.module_id),
        content: Value::String(text),
        kind: "text".into(),
        fixed: false,
        protection: "elastic".into(),
        priority: 1.0,
        required_terms: required.into_iter().collect(),
        dependency_group: None,
        metadata,
    });
    Ok((pinned, pinned_tokens + after))
}

fn compress_text(id: &str, text: &str, target: i32, counts: &CountContext<'_>) -> String {
    match id {
        "builtin.text.normalize_whitespace.v1" => {
            text.split_whitespace().collect::<Vec<_>>().join(" ")
        }
        "builtin.text.deduplicate_blocks.v1" => {
            let mut seen = BTreeSet::new();
            text.split("\n\n")
                .filter(|b| seen.insert(b.trim().to_string()))
                .collect::<Vec<_>>()
                .join("\n\n")
        }
        "builtin.text.extractive_sentence_rank.v1" => select_sentences(text, target, counts),
        "builtin.text.boundary_truncate.v1" => truncate(text, target, counts),
        _ => text.to_string(),
    }
}

fn select_sentences(text: &str, target: i32, counts: &CountContext<'_>) -> String {
    let mut result = String::new();
    for sentence in text.split_inclusive(['.', '!', '?', '。', '！', '？']) {
        let next = if result.is_empty() {
            sentence.trim().to_string()
        } else {
            format!("{} {}", result, sentence.trim())
        };
        if counts.count_text(&next) > target {
            break;
        }
        result = next;
    }
    if result.is_empty() {
        truncate(text, target, counts)
    } else {
        result
    }
}

fn truncate(text: &str, target: i32, counts: &CountContext<'_>) -> String {
    if counts.external.is_none() && uses_char_estimator(counts.tokenizer_id) {
        return truncate_char_estimator(text, target);
    }
    if target <= 0 {
        return String::new();
    }
    let mut out = String::new();
    for ch in text.chars() {
        let mut candidate = out.clone();
        candidate.push(ch);
        if counts.count_text(&candidate) > target {
            break;
        }
        out.push(ch);
    }
    out.trim_end().to_string()
}

fn uses_char_estimator(tokenizer_id: &str) -> bool {
    tokenizer_id == "cjk_aware_char_estimator" || tokenizer_id.starts_with("tiktoken_")
}

fn is_cjk_estimator_char(ch: char) -> bool {
    matches!(
        ch as u32,
        0x3400..=0x4DBF
            | 0x4E00..=0x9FFF
            | 0x3000..=0x30FF
            | 0xFF00..=0xFFEF
            | 0xAC00..=0xD7AF
    )
}

fn count_char_estimator(text: &str) -> i32 {
    let mut cjk = 0;
    let mut other = 0;
    for ch in text.chars() {
        if is_cjk_estimator_char(ch) {
            cjk += 1;
        } else {
            other += ch.len_utf16() as i32;
        }
    }
    cjk + (other + 3) / 4
}

fn truncate_char_estimator(text: &str, target: i32) -> String {
    if target <= 0 {
        return String::new();
    }
    let mut out = String::new();
    let mut cjk = 0;
    let mut other = 0;
    for ch in text.chars() {
        let (next_cjk, next_other) = if is_cjk_estimator_char(ch) {
            (cjk + 1, other)
        } else {
            (cjk, other + ch.len_utf16() as i32)
        };
        if next_cjk + (next_other + 3) / 4 > target {
            break;
        }
        cjk = next_cjk;
        other = next_other;
        out.push(ch);
    }
    out.trim_end().to_string()
}

fn estimate_text(text: &str, tokenizer_id: &str) -> i32 {
    if uses_char_estimator(tokenizer_id) {
        count_char_estimator(text)
    } else {
        count_text(text)
    }
}

pub fn count_text(text: &str) -> i32 {
    let mut tokens = 0;
    let mut in_word = false;
    for ch in text.chars() {
        let word = ch.is_alphanumeric() || ch == '_';
        if (word && !in_word) || (!word && !ch.is_whitespace()) {
            tokens += 1;
        }
        in_word = word;
    }
    tokens
}
fn render(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        v => serde_json::to_string(v).unwrap_or_default(),
    }
}

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn timestamp_now() -> String {
    let duration = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    format_utc_timestamp(duration.as_secs(), duration.subsec_millis())
}

fn format_utc_timestamp(unix_seconds: u64, milliseconds: u32) -> String {
    let days = (unix_seconds / 86_400) as i64;
    let seconds_in_day = unix_seconds % 86_400;
    let hour = seconds_in_day / 3_600;
    let minute = (seconds_in_day % 3_600) / 60;
    let second = seconds_in_day % 60;

    // Convert days since 1970-01-01 to the proleptic Gregorian calendar.
    let z = days + 719_468;
    let era = z / 146_097;
    let day_of_era = z - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = month_prime + if month_prime < 10 { 3 } else { -9 };
    if month <= 2 {
        year += 1;
    }

    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{milliseconds:03}Z")
}

fn calibration_key(model: &ModelProfile) -> String {
    calibration_key_parts(
        &model.model_profile_id,
        &model.tokenizer_id,
        &model.tokenizer_version,
    )
}

fn calibration_key_parts(model: &str, tokenizer: &str, version: &str) -> String {
    format!("{model}\0{tokenizer}\0{version}")
}

fn validate_definition(definition: &ArenaDefinition) -> Result<(), ContextLeaseError> {
    if definition.arena_id.trim().is_empty()
        || definition.schema_version.trim().is_empty()
        || definition.policy_version.trim().is_empty()
        || definition.admission_policy.trim().is_empty()
        || definition.modules.is_empty()
        || definition.framework_reserve_tokens < 0
    {
        return Err(ContextLeaseError::new(
            "layout_validation_error",
            "arena and modules are required",
        ));
    }
    let mut ids = BTreeSet::new();
    for m in &definition.modules {
        if m.module_id.trim().is_empty() || !ids.insert(m.module_id.clone()) {
            return Err(ContextLeaseError::new(
                "layout_validation_error",
                "module ids must be unique",
            ));
        }
        if !(0 <= m.floor_tokens
            && m.floor_tokens <= m.target_tokens
            && m.target_tokens <= m.max_tokens)
        {
            return Err(ContextLeaseError::new(
                "layout_validation_error",
                format!("{} invalid floor/target/max", m.module_id),
            ));
        }
        if m.weight <= 0.0 {
            return Err(ContextLeaseError::new(
                "layout_validation_error",
                "weight must be positive",
            ));
        }
        validate_choice(
            "lifecycle",
            &m.lifecycle,
            &["static", "session", "request", "turn", "ephemeral"],
        )?;
        validate_choice(
            "allocation",
            &m.allocation,
            &["fixed", "weighted", "priority", "elastic"],
        )?;
        validate_choice("protection", &m.protection, &["pinned", "mixed", "elastic"])?;
        validate_choice(
            "reclaim",
            &m.reclaim,
            &["none", "builtin_pipeline", "semantic_pipeline", "custom"],
        )?;
        validate_choice(
            "render_target",
            &m.render_target,
            &["text", "messages", "tool_schema", "structured"],
        )?;
        if m.can_borrow && m.max_tokens > m.target_tokens && m.reclaim_pipeline.is_empty() {
            return Err(ContextLeaseError::new(
                "layout_validation_error",
                format!("{} borrowing requires reclaim pipeline", m.module_id),
            ));
        }
        if m.reclaim_pipeline
            .iter()
            .filter(|step| is_semantic_algorithm(&step.algorithm_id))
            .count()
            > 1
        {
            return Err(ContextLeaseError::new(
                "layout_validation_error",
                format!(
                    "{} native two-phase pipelines support one semantic step",
                    m.module_id
                ),
            ));
        }
        if m.reclaim_pipeline
            .iter()
            .any(|step| step.algorithm_id.trim().is_empty())
        {
            return Err(ContextLeaseError::new(
                "layout_validation_error",
                format!("{} reclaim algorithm id must not be empty", m.module_id),
            ));
        }
    }
    Ok(())
}
fn validate_model(model: &ModelProfile) -> Result<(), ContextLeaseError> {
    if model.model_profile_id.trim().is_empty()
        || model.context_limit_tokens <= 0
        || model.reserved_output_tokens < 0
        || model.tokenizer_id.trim().is_empty()
        || model.tokenizer_version.trim().is_empty()
    {
        return Err(ContextLeaseError::new(
            "configuration_error",
            "invalid model profile",
        ));
    }
    validate_choice(
        "count_mode",
        &model.count_mode,
        &["exact", "estimated", "hybrid"],
    )
}
fn validate_plan(plan: &PrepareRequest) -> Result<(), ContextLeaseError> {
    if plan.schema_version != "1.0" {
        return Err(ContextLeaseError::new(
            "configuration_error",
            format!(
                "unsupported context plan schema_version: {}",
                plan.schema_version
            ),
        ));
    }
    Ok(())
}
fn validate_choice(field: &str, value: &str, allowed: &[&str]) -> Result<(), ContextLeaseError> {
    if allowed.contains(&value) {
        Ok(())
    } else {
        Err(ContextLeaseError::new(
            "configuration_error",
            format!("invalid {field}: {value}"),
        ))
    }
}
fn validate_model_budget(
    definition: &ArenaDefinition,
    input: i32,
) -> Result<(), ContextLeaseError> {
    let available = input - definition.framework_reserve_tokens;
    if available <= 0
        || definition
            .modules
            .iter()
            .map(|m| m.floor_tokens)
            .sum::<i32>()
            > available
    {
        return Err(ContextLeaseError::new(
            "layout_validation_error",
            "model budget cannot satisfy module floors",
        ));
    }
    Ok(())
}
fn validate_contributions(
    definition: &ArenaDefinition,
    values: Vec<ModuleContribution>,
) -> Result<HashMap<String, ModuleContribution>, ContextLeaseError> {
    let known: BTreeSet<&str> = definition
        .modules
        .iter()
        .map(|m| m.module_id.as_str())
        .collect();
    let mut out = HashMap::new();
    for value in values {
        if !known.contains(value.module_id.as_str()) {
            return Err(ContextLeaseError::new(
                "configuration_error",
                format!("unknown contribution module: {}", value.module_id),
            ));
        }
        if out.contains_key(&value.module_id) {
            return Err(ContextLeaseError::new(
                "configuration_error",
                format!("duplicate contribution module: {}", value.module_id),
            ));
        }
        if value
            .observed_demand_tokens
            .is_some_and(|tokens| tokens < 0)
        {
            return Err(ContextLeaseError::new(
                "configuration_error",
                "observed demand must be non-negative",
            ));
        }
        let mut ids = BTreeSet::new();
        for chunk in &value.chunks {
            if chunk.chunk_id.trim().is_empty() || chunk.kind.trim().is_empty() {
                return Err(ContextLeaseError::new(
                    "configuration_error",
                    "chunk id and kind must be non-empty",
                ));
            }
            if !ids.insert(chunk.chunk_id.clone()) {
                return Err(ContextLeaseError::new(
                    "configuration_error",
                    format!(
                        "module {} contains duplicate chunk_id {}",
                        value.module_id, chunk.chunk_id
                    ),
                ));
            }
            validate_choice(
                "chunk protection",
                &chunk.protection,
                &["pinned", "mixed", "elastic"],
            )?;
        }
        out.insert(value.module_id.clone(), value);
    }
    Ok(out)
}
fn pressure(used: i32, budget: i32) -> String {
    let ratio = used as f64 / budget.max(1) as f64;
    if ratio > 1.0 {
        "overflow"
    } else if ratio >= 0.9 {
        "critical"
    } else if ratio >= 0.7 {
        "elevated"
    } else {
        "normal"
    }
    .into()
}
fn yes() -> bool {
    true
}
fn one_f64() -> f64 {
    1.0
}
fn mixed() -> String {
    "mixed".into()
}
fn elastic() -> String {
    "elastic".into()
}
fn v1() -> String {
    "1.0".into()
}
fn policy_v1() -> String {
    "1".into()
}
fn tokenizer() -> String {
    "regex-estimator-v1".into()
}
fn tokenizer_v1() -> String {
    "1".into()
}
fn estimated_count_mode() -> String {
    "estimated".into()
}
fn request_lifecycle() -> String {
    "request".into()
}
fn weighted_allocation() -> String {
    "weighted".into()
}
fn builtin_reclaim() -> String {
    "builtin_pipeline".into()
}
fn text_render_target() -> String {
    "text".into()
}
fn text_kind() -> String {
    "text".into()
}
fn reject_admission() -> String {
    "reject".into()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utc_timestamp_format_is_rfc3339() {
        assert_eq!(format_utc_timestamp(0, 0), "1970-01-01T00:00:00.000Z");
        assert_eq!(
            format_utc_timestamp(946_684_800, 123),
            "2000-01-01T00:00:00.123Z"
        );
    }

    fn module(id: &str, floor: i32, target: i32, max: i32, order: i32) -> ModuleDefinition {
        ModuleDefinition {
            module_id: id.into(),
            floor_tokens: floor,
            target_tokens: target,
            max_tokens: max,
            order,
            weight: 1.0,
            lifecycle: "request".into(),
            allocation: "weighted".into(),
            protection: "mixed".into(),
            reclaim: "builtin_pipeline".into(),
            render_target: "text".into(),
            can_borrow: true,
            can_lend: true,
            reclaim_pipeline: vec![CompressionStepSpec {
                algorithm_id: "builtin.text.boundary_truncate.v1".into(),
                options: BTreeMap::new(),
            }],
            metadata: BTreeMap::new(),
        }
    }
    #[test]
    fn borrowing_is_deterministic() {
        let arena = ContextLeaseArena::new(ArenaDefinition {
            arena_id: "test".into(),
            modules: vec![module("system", 1, 4, 4, 0), module("memory", 1, 2, 8, 1)],
            schema_version: "1.0".into(),
            policy_version: "1".into(),
            framework_reserve_tokens: 0,
            admission_policy: "reject".into(),
            metadata: BTreeMap::new(),
        })
        .unwrap();
        let result = arena
            .prepare(PrepareRequest {
                schema_version: "1.0".into(),
                model: ModelProfile {
                    model_profile_id: "tiny".into(),
                    context_limit_tokens: 12,
                    reserved_output_tokens: 2,
                    tokenizer_id: "regex-estimator-v1".into(),
                    tokenizer_version: "1".into(),
                    count_mode: "estimated".into(),
                },
                contributions: vec![ModuleContribution {
                    module_id: "memory".into(),
                    chunks: vec![PromptChunk {
                        chunk_id: "m".into(),
                        content: Value::String("one two three four five six".into()),
                        kind: "text".into(),
                        fixed: false,
                        protection: "elastic".into(),
                        priority: 1.0,
                        required_terms: vec![],
                        dependency_group: None,
                        metadata: BTreeMap::new(),
                    }],
                    observed_demand_tokens: None,
                    metadata: BTreeMap::new(),
                }],
                request_id: Some("r1".into()),
            })
            .unwrap();
        assert!(result.prompt_tokens <= result.input_budget_tokens);
        assert_eq!(result.leases[0].borrower_module_id, "memory");
    }

    #[test]
    fn fixed_chunk_is_never_compressed() {
        let chunks = vec![
            PromptChunk {
                chunk_id: "fixed".into(),
                content: Value::String("must remain".into()),
                kind: "text".into(),
                fixed: true,
                protection: "elastic".into(),
                priority: 1.0,
                required_terms: vec![],
                dependency_group: None,
                metadata: BTreeMap::new(),
            },
            PromptChunk {
                chunk_id: "elastic".into(),
                content: Value::String("can shrink".into()),
                kind: "text".into(),
                fixed: false,
                protection: "elastic".into(),
                priority: 1.0,
                required_terms: vec![],
                dependency_group: None,
                metadata: BTreeMap::new(),
            },
        ];
        let counts = CountContext {
            tokenizer_id: "regex-estimator-v1",
            external: None,
            safety_multiplier: 1.0,
            failed: Cell::new(false),
        };
        let error = compress_module(
            &module("memory", 0, 1, 4, 0),
            chunks,
            1,
            &HashMap::new(),
            &counts,
        )
        .unwrap_err();
        assert_eq!(error.code, "admission_error");
    }

    #[test]
    fn semantic_prepare_is_two_phase_and_preserves_required_terms() {
        let mut memory = module("memory", 0, 1, 8, 0);
        memory.reclaim_pipeline = vec![
            CompressionStepSpec {
                algorithm_id: "builtin.semantic.summary.v1".into(),
                options: BTreeMap::from([("provider".into(), Value::String("mock".into()))]),
            },
            CompressionStepSpec {
                algorithm_id: "builtin.text.boundary_truncate.v1".into(),
                options: BTreeMap::new(),
            },
        ];
        let arena = ContextLeaseArena::new(ArenaDefinition {
            arena_id: "semantic".into(),
            modules: vec![memory],
            schema_version: "1.0".into(),
            policy_version: "1".into(),
            framework_reserve_tokens: 0,
            admission_policy: "reject".into(),
            metadata: BTreeMap::new(),
        })
        .unwrap();
        let request = PrepareRequest {
            schema_version: "1.0".into(),
            model: ModelProfile {
                model_profile_id: "tiny".into(),
                context_limit_tokens: 4,
                reserved_output_tokens: 0,
                tokenizer_id: "regex-estimator-v1".into(),
                tokenizer_version: "1".into(),
                count_mode: "estimated".into(),
            },
            contributions: vec![ModuleContribution {
                module_id: "memory".into(),
                chunks: vec![PromptChunk {
                    chunk_id: "facts".into(),
                    content: Value::String("alpha beta gamma delta epsilon zeta".into()),
                    kind: "text".into(),
                    fixed: false,
                    protection: "elastic".into(),
                    priority: 1.0,
                    required_terms: vec!["alpha".into()],
                    dependency_group: None,
                    metadata: BTreeMap::new(),
                }],
                observed_demand_tokens: None,
                metadata: BTreeMap::new(),
            }],
            request_id: Some("semantic-r1".into()),
        };
        let begin = arena.prepare_begin(request.clone()).unwrap();
        assert_eq!(begin.status, "needs_semantic");
        assert_eq!(begin.semantic_requests.len(), 1);
        assert_eq!(begin.semantic_requests[0].provider_id, "mock");
        let prepared = arena
            .prepare_commit(
                request,
                vec![SemanticResult {
                    semantic_request_id: begin.semantic_requests[0].semantic_request_id.clone(),
                    content: "alpha beta".into(),
                }],
            )
            .unwrap();
        assert!(prepared.rendered.contains("alpha"));
        assert!(prepared.prompt_tokens <= prepared.input_budget_tokens);
    }

    #[test]
    fn cjk_char_estimator_matches_host_contract() {
        let tokenizer_id = "cjk_aware_char_estimator";
        let counts = CountContext {
            tokenizer_id,
            external: None,
            safety_multiplier: 1.0,
            failed: Cell::new(false),
        };
        assert_eq!(counts.count_text("中文abcd"), 3);
        let truncated = truncate("中文abcdefgh", 3, &counts);
        assert!(counts.count_text(&truncated) <= 3);
        assert_eq!(truncated, "中文abcd");
    }

    #[test]
    fn structured_plan_native_telemetry_and_usage_calibration_are_owned_by_core() {
        let arena = ContextLeaseArena::new(ArenaDefinition {
            arena_id: "trustworthy".into(),
            modules: vec![module("memory", 0, 8, 8, 0)],
            schema_version: "1.0".into(),
            policy_version: "1".into(),
            framework_reserve_tokens: 0,
            admission_policy: "reject".into(),
            metadata: BTreeMap::new(),
        })
        .unwrap();
        let make_request = |request_id: &str| PrepareRequest {
            schema_version: "1.0".into(),
            model: ModelProfile {
                model_profile_id: "calibrated".into(),
                context_limit_tokens: 8,
                reserved_output_tokens: 0,
                tokenizer_id: "regex-estimator-v1".into(),
                tokenizer_version: "1".into(),
                count_mode: "estimated".into(),
            },
            contributions: vec![ModuleContribution {
                module_id: "memory".into(),
                chunks: vec![PromptChunk {
                    chunk_id: "facts".into(),
                    content: Value::String("one two".into()),
                    kind: "text".into(),
                    fixed: false,
                    protection: "elastic".into(),
                    priority: 1.0,
                    required_terms: vec![],
                    dependency_group: None,
                    metadata: BTreeMap::new(),
                }],
                observed_demand_tokens: None,
                metadata: BTreeMap::new(),
            }],
            request_id: Some(request_id.into()),
        };
        let first = arena.prepare(make_request("usage-1")).unwrap();
        assert_eq!(first.prompt_tokens, 2);
        assert_eq!(first.module_plans[0].chunks[0].chunk_id, "facts");
        assert!(!first.trace_events.is_empty());
        assert_eq!(
            arena.snapshot().unwrap().unwrap().request_id.as_deref(),
            Some("usage-1")
        );
        assert!(!arena.events_after(0, 100).unwrap().is_empty());
        let calibration = arena
            .record_usage(UsageObservation {
                request_id: "usage-1".into(),
                actual_input_tokens: 4,
            })
            .unwrap();
        assert_eq!(calibration.safety_multiplier, 2.0);
        let second = arena.prepare(make_request("usage-2")).unwrap();
        assert_eq!(second.prompt_tokens, 4);
        assert_eq!(second.calibration.unwrap().sample_count, 1);
    }
}
