use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fmt;
use std::sync::Mutex;

pub const CORE_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CompressionStepSpec {
    pub algorithm_id: String,
    #[serde(default)]
    pub options: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleDefinition {
    pub module_id: String,
    pub floor_tokens: i32,
    pub target_tokens: i32,
    pub max_tokens: i32,
    #[serde(default)]
    pub order: i32,
    #[serde(default = "one_f64")]
    pub weight: f64,
    #[serde(default = "mixed")]
    pub protection: String,
    #[serde(default = "yes")]
    pub can_borrow: bool,
    #[serde(default = "yes")]
    pub can_lend: bool,
    #[serde(default)]
    pub reclaim_pipeline: Vec<CompressionStepSpec>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArenaDefinition {
    pub arena_id: String,
    pub modules: Vec<ModuleDefinition>,
    #[serde(default = "v1")]
    pub schema_version: String,
    #[serde(default = "policy_v1")]
    pub policy_version: String,
    #[serde(default)]
    pub framework_reserve_tokens: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelProfile {
    pub model_profile_id: String,
    pub context_limit_tokens: i32,
    pub reserved_output_tokens: i32,
    #[serde(default = "tokenizer")]
    pub tokenizer_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptChunk {
    pub chunk_id: String,
    pub content: Value,
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
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleContribution {
    pub module_id: String,
    #[serde(default)]
    pub chunks: Vec<PromptChunk>,
    #[serde(default)]
    pub observed_demand_tokens: Option<i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrepareRequest {
    pub model: ModelProfile,
    #[serde(default)]
    pub contributions: Vec<ModuleContribution>,
    #[serde(default)]
    pub request_id: Option<String>,
}

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
    pub release_pipeline: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModuleUsage {
    pub module_id: String,
    pub demanded_tokens: i32,
    pub allocated_tokens: i32,
    pub used_tokens: i32,
    pub fixed_tokens: i32,
    pub pinned_tokens: i32,
    pub compressed_from_tokens: i32,
    pub compressed_to_tokens: i32,
    pub change_rate: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PreparedContext {
    pub schema_version: String,
    pub core_version: String,
    pub arena_id: String,
    pub request_id: String,
    pub layout_hash: String,
    pub policy_version: String,
    pub rendered: String,
    pub prompt_tokens: i32,
    pub input_budget_tokens: i32,
    pub slack_tokens: i32,
    pub pressure: String,
    pub allocations: Vec<ModuleAllocation>,
    pub leases: Vec<Lease>,
    pub modules: Vec<ModuleUsage>,
}

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

#[derive(Default)]
struct ArenaState {
    request_seq: u64,
    previous_usage: HashMap<String, i32>,
    active_leases: HashMap<String, Lease>,
}

pub struct ContextLeaseArena {
    definition: ArenaDefinition,
    layout_hash: String,
    order: Vec<usize>,
    state: Mutex<ArenaState>,
}

impl ContextLeaseArena {
    pub fn new(definition: ArenaDefinition) -> Result<Self, ContextLeaseError> {
        validate_definition(&definition)?;
        let canonical = serde_json::to_vec(&definition)
            .map_err(|e| ContextLeaseError::new("serialization_error", e.to_string()))?;
        let layout_hash = format!("{:x}", Sha256::digest(canonical))[..24].to_string();
        let mut order: Vec<usize> = (0..definition.modules.len()).collect();
        order.sort_by(|a, b| {
            let a = &definition.modules[*a];
            let b = &definition.modules[*b];
            (a.order, &a.module_id).cmp(&(b.order, &b.module_id))
        });
        Ok(Self {
            definition,
            layout_hash,
            order,
            state: Mutex::new(ArenaState::default()),
        })
    }

    pub fn prepare(&self, request: PrepareRequest) -> Result<PreparedContext, ContextLeaseError> {
        self.prepare_with_semantic_results(request, &[])
    }

    pub fn prepare_begin(
        &self,
        request: PrepareRequest,
    ) -> Result<PrepareBeginOutcome, ContextLeaseError> {
        let semantic_requests = self.plan_semantic_requests(&request)?;
        if semantic_requests.is_empty() {
            return Ok(PrepareBeginOutcome {
                status: "ready".into(),
                prepared: Some(self.prepare(request)?),
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
        let expected = self.plan_semantic_requests(&request)?;
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
        self.prepare_with_semantic_results(request, &results)
    }

    fn prepare_with_semantic_results(
        &self,
        request: PrepareRequest,
        results: &[SemanticResult],
    ) -> Result<PreparedContext, ContextLeaseError> {
        let semantic_results: HashMap<&str, &str> = results
            .iter()
            .map(|result| (result.semantic_request_id.as_str(), result.content.as_str()))
            .collect();
        let input_budget =
            request.model.context_limit_tokens - request.model.reserved_output_tokens;
        let tokenizer_id = request.model.tokenizer_id.as_str();
        let contributions = validate_contributions(&self.definition, request.contributions)?;
        let render_overhead =
            render_separator_tokens(&self.definition, &contributions, tokenizer_id);
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
                            .map(|x| count_content_with_tokenizer(&x.content, tokenizer_id))
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
        let mut state = self
            .state
            .lock()
            .map_err(|_| ContextLeaseError::new("arena_poisoned", "arena state lock poisoned"))?;
        state.request_seq += 1;
        let request_id = request
            .request_id
            .filter(|x| !x.trim().is_empty())
            .unwrap_or_else(|| format!("{}:{}", self.definition.arena_id, state.request_seq));
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
                .map(|c| count_content_with_tokenizer(&c.content, tokenizer_id))
                .sum();
            let (chunks, after) = if before > allocation.allocated_tokens {
                compress_module(
                    module,
                    chunks,
                    allocation.allocated_tokens,
                    &semantic_results,
                    tokenizer_id,
                )?
            } else {
                (chunks, before)
            };
            let fixed_tokens = chunks
                .iter()
                .filter(|c| c.fixed)
                .map(|c| count_content_with_tokenizer(&c.content, tokenizer_id))
                .sum();
            let pinned_tokens = chunks
                .iter()
                .filter(|c| module.protection == "pinned" || c.protection == "pinned")
                .map(|c| count_content_with_tokenizer(&c.content, tokenizer_id))
                .sum();
            let previous = state
                .previous_usage
                .insert(module.module_id.clone(), after)
                .unwrap_or(after);
            module_usage.push(ModuleUsage {
                module_id: module.module_id.clone(),
                demanded_tokens: allocation.demanded_tokens,
                allocated_tokens: allocation.allocated_tokens,
                used_tokens: after,
                fixed_tokens,
                pinned_tokens,
                compressed_from_tokens: before,
                compressed_to_tokens: after,
                change_rate: (after - previous) as f64 / previous.max(1) as f64,
            });
            final_chunks.insert(module.module_id.clone(), chunks);
        }
        state.active_leases = leases
            .iter()
            .cloned()
            .map(|l| (l.lease_id.clone(), l))
            .collect();
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
        let prompt_tokens = count_text_with_tokenizer(&rendered, tokenizer_id);
        let usable = input_budget - self.definition.framework_reserve_tokens;
        if prompt_tokens > usable {
            return Err(ContextLeaseError::new(
                "admission_error",
                "rendered context exceeds usable budget",
            ));
        }
        Ok(PreparedContext {
            schema_version: "1.0".into(),
            core_version: CORE_VERSION.into(),
            arena_id: self.definition.arena_id.clone(),
            request_id,
            layout_hash: self.layout_hash.clone(),
            policy_version: self.definition.policy_version.clone(),
            rendered,
            prompt_tokens,
            input_budget_tokens: usable,
            slack_tokens: usable - prompt_tokens,
            pressure: pressure(prompt_tokens, usable),
            allocations,
            leases,
            modules: module_usage,
        })
    }

    fn plan_semantic_requests(
        &self,
        request: &PrepareRequest,
    ) -> Result<Vec<SemanticRequest>, ContextLeaseError> {
        let input_budget =
            request.model.context_limit_tokens - request.model.reserved_output_tokens;
        let tokenizer_id = request.model.tokenizer_id.as_str();
        let contributions =
            validate_contributions(&self.definition, request.contributions.clone())?;
        let render_overhead =
            render_separator_tokens(&self.definition, &contributions, tokenizer_id);
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
                            .map(|chunk| count_content_with_tokenizer(&chunk.content, tokenizer_id))
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
                .map(|chunk| count_content_with_tokenizer(&chunk.content, tokenizer_id))
                .sum();
            let allocation = allocation_by_id[module.module_id.as_str()];
            if before > allocation {
                requests.extend(collect_semantic_requests(
                    module,
                    chunks,
                    allocation,
                    tokenizer_id,
                )?);
            }
        }
        Ok(requests)
    }
}

fn render_separator_tokens(
    definition: &ArenaDefinition,
    contributions: &HashMap<String, ModuleContribution>,
    tokenizer_id: &str,
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
    count_text_with_tokenizer(&"\n\n".repeat(rendered_module_count - 1), tokenizer_id)
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
        release_pipeline: borrower
            .reclaim_pipeline
            .iter()
            .map(|s| s.algorithm_id.clone())
            .collect(),
    }
}

fn collect_semantic_requests(
    module: &ModuleDefinition,
    chunks: Vec<PromptChunk>,
    allocation: i32,
    tokenizer_id: &str,
) -> Result<Vec<SemanticRequest>, ContextLeaseError> {
    let (protected, elastic): (Vec<_>, Vec<_>) = chunks.into_iter().partition(|chunk| {
        chunk.fixed || module.protection == "pinned" || chunk.protection == "pinned"
    });
    let protected_tokens: i32 = protected
        .iter()
        .map(|chunk| count_content_with_tokenizer(&chunk.content, tokenizer_id))
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
        if count_text_with_tokenizer(&text, tokenizer_id) <= target {
            break;
        }
        if is_semantic_algorithm(&step.algorithm_id) {
            return semantic_requests_for_step(module, step, &text, target, &required);
        }
        let candidate = compress_text(&step.algorithm_id, &text, target, tokenizer_id);
        if count_text_with_tokenizer(&candidate, tokenizer_id)
            <= count_text_with_tokenizer(&text, tokenizer_id)
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
    tokenizer_id: &str,
) -> Result<(Vec<PromptChunk>, i32), ContextLeaseError> {
    let (mut pinned, elastic): (Vec<_>, Vec<_>) = chunks
        .into_iter()
        .partition(|c| c.fixed || module.protection == "pinned" || c.protection == "pinned");
    let pinned_tokens: i32 = pinned
        .iter()
        .map(|c| count_content_with_tokenizer(&c.content, tokenizer_id))
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
        if count_text_with_tokenizer(&text, tokenizer_id) <= target {
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
                        && count_text_with_tokenizer(candidate, tokenizer_id)
                            <= count_text_with_tokenizer(&text, tokenizer_id)
                        && required.iter().all(|term| candidate.contains(term))
                })
                .collect();
            candidates.sort_by_key(|candidate| count_text_with_tokenizer(candidate, tokenizer_id));
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
            let candidate = compress_text(&step.algorithm_id, &text, target, tokenizer_id);
            if count_text_with_tokenizer(&candidate, tokenizer_id)
                <= count_text_with_tokenizer(&text, tokenizer_id)
                && required.iter().all(|term| candidate.contains(term))
            {
                text = candidate;
            }
        }
    }
    let after = count_text_with_tokenizer(&text, tokenizer_id);
    if after > target {
        return Err(ContextLeaseError::new(
            "admission_error",
            format!("{} reclaim target unmet", module.module_id),
        ));
    }
    pinned.push(PromptChunk {
        chunk_id: format!("{}:compressed", module.module_id),
        content: Value::String(text),
        fixed: false,
        protection: "elastic".into(),
        priority: 1.0,
        required_terms: required.into_iter().collect(),
        dependency_group: None,
    });
    Ok((pinned, pinned_tokens + after))
}

fn compress_text(id: &str, text: &str, target: i32, tokenizer_id: &str) -> String {
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
        "builtin.text.extractive_sentence_rank.v1" => select_sentences(text, target, tokenizer_id),
        "builtin.text.boundary_truncate.v1" => truncate(text, target, tokenizer_id),
        _ => text.to_string(),
    }
}

fn select_sentences(text: &str, target: i32, tokenizer_id: &str) -> String {
    let mut result = String::new();
    for sentence in text.split_inclusive(['.', '!', '?', '。', '！', '？']) {
        let next = if result.is_empty() {
            sentence.trim().to_string()
        } else {
            format!("{} {}", result, sentence.trim())
        };
        if count_text_with_tokenizer(&next, tokenizer_id) > target {
            break;
        }
        result = next;
    }
    if result.is_empty() {
        truncate(text, target, tokenizer_id)
    } else {
        result
    }
}

fn truncate(text: &str, target: i32, tokenizer_id: &str) -> String {
    if uses_char_estimator(tokenizer_id) {
        return truncate_char_estimator(text, target);
    }
    if target <= 0 {
        return String::new();
    }
    let mut out = String::new();
    let mut tokens = 0;
    let mut in_word = false;
    for ch in text.chars() {
        let word = ch.is_alphanumeric() || ch == '_';
        let adds = if word {
            if in_word {
                0
            } else {
                1
            }
        } else if ch.is_whitespace() {
            0
        } else {
            1
        };
        if tokens + adds > target {
            break;
        }
        tokens += adds;
        in_word = word;
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

fn count_text_with_tokenizer(text: &str, tokenizer_id: &str) -> i32 {
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
        if word && !in_word {
            tokens += 1;
        } else if !word && !ch.is_whitespace() {
            tokens += 1;
        }
        in_word = word;
    }
    tokens
}
fn count_content_with_tokenizer(value: &Value, tokenizer_id: &str) -> i32 {
    match value {
        Value::String(s) => count_text_with_tokenizer(s, tokenizer_id),
        Value::Null => 0,
        value => count_text_with_tokenizer(
            &serde_json::to_string(value).unwrap_or_default(),
            tokenizer_id,
        ),
    }
}
fn render(value: &Value) -> String {
    match value {
        Value::String(s) => s.clone(),
        v => serde_json::to_string(v).unwrap_or_default(),
    }
}

fn validate_definition(definition: &ArenaDefinition) -> Result<(), ContextLeaseError> {
    if definition.arena_id.trim().is_empty() || definition.modules.is_empty() {
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
    }
    Ok(())
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
        if !known.contains(value.module_id.as_str()) || out.contains_key(&value.module_id) {
            return Err(ContextLeaseError::new(
                "configuration_error",
                "unknown or duplicate contribution",
            ));
        }
        let mut ids = BTreeSet::new();
        if value.chunks.iter().any(|c| !ids.insert(c.chunk_id.clone())) {
            return Err(ContextLeaseError::new(
                "configuration_error",
                "duplicate chunk id",
            ));
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

#[cfg(test)]
mod tests {
    use super::*;
    fn module(id: &str, floor: i32, target: i32, max: i32, order: i32) -> ModuleDefinition {
        ModuleDefinition {
            module_id: id.into(),
            floor_tokens: floor,
            target_tokens: target,
            max_tokens: max,
            order,
            weight: 1.0,
            protection: "mixed".into(),
            can_borrow: true,
            can_lend: true,
            reclaim_pipeline: vec![CompressionStepSpec {
                algorithm_id: "builtin.text.boundary_truncate.v1".into(),
                options: BTreeMap::new(),
            }],
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
        })
        .unwrap();
        let result = arena
            .prepare(PrepareRequest {
                model: ModelProfile {
                    model_profile_id: "tiny".into(),
                    context_limit_tokens: 12,
                    reserved_output_tokens: 2,
                    tokenizer_id: "regex-estimator-v1".into(),
                },
                contributions: vec![ModuleContribution {
                    module_id: "memory".into(),
                    chunks: vec![PromptChunk {
                        chunk_id: "m".into(),
                        content: Value::String("one two three four five six".into()),
                        fixed: false,
                        protection: "elastic".into(),
                        priority: 1.0,
                        required_terms: vec![],
                        dependency_group: None,
                    }],
                    observed_demand_tokens: None,
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
                fixed: true,
                protection: "elastic".into(),
                priority: 1.0,
                required_terms: vec![],
                dependency_group: None,
            },
            PromptChunk {
                chunk_id: "elastic".into(),
                content: Value::String("can shrink".into()),
                fixed: false,
                protection: "elastic".into(),
                priority: 1.0,
                required_terms: vec![],
                dependency_group: None,
            },
        ];
        let error = compress_module(
            &module("memory", 0, 1, 4, 0),
            chunks,
            1,
            &HashMap::new(),
            "regex-estimator-v1",
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
        })
        .unwrap();
        let request = PrepareRequest {
            model: ModelProfile {
                model_profile_id: "tiny".into(),
                context_limit_tokens: 4,
                reserved_output_tokens: 0,
                tokenizer_id: "regex-estimator-v1".into(),
            },
            contributions: vec![ModuleContribution {
                module_id: "memory".into(),
                chunks: vec![PromptChunk {
                    chunk_id: "facts".into(),
                    content: Value::String("alpha beta gamma delta epsilon zeta".into()),
                    fixed: false,
                    protection: "elastic".into(),
                    priority: 1.0,
                    required_terms: vec!["alpha".into()],
                    dependency_group: None,
                }],
                observed_demand_tokens: None,
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
        assert_eq!(count_text_with_tokenizer("中文abcd", tokenizer_id), 3);
        let truncated = truncate("中文abcdefgh", 3, tokenizer_id);
        assert!(count_text_with_tokenizer(&truncated, tokenizer_id) <= 3);
        assert_eq!(truncated, "中文abcd");
    }
}
