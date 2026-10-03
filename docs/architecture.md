# Architecture and Learning Objectives

## Project objectives

This project has two equally important objectives:

1. Build a credible, production-minded agentic analytics system over job-application data.
2. Use that system as a hands-on learning vehicle for modern agentic AI engineering.

Optimise for sound engineering and visibility into how the technologies work. The implementation should make decisions understandable, explainable and comparable through traces and experiments.

This document describes the intended architecture, not implemented functionality. Retrieval, data semantics and indexing remain authoritative in their respective contracts.

## Learning objectives

The two primary learning goals are **LangGraph / LangSmith** and **SLMs / open-weight / closed-weight models**. They are equally important. Retrieval, agent architecture, LLMOps and production engineering support these goals.

Model size, access to weights and deployment location are independent dimensions. Open-weight models may be large or hosted; closed-weight models may be small. Keep these dimensions explicit in experiment configuration and comparisons.

| Area | Practical experience |
|---|---|
| LangGraph | State management, nodes, edges, conditional execution, parallel branches, loops, retries, tools, checkpointing, conversational state and human-in-the-loop where relevant |
| LangSmith | Tracing, datasets, evaluators, experiments, regression evaluation, prompt/model comparison, latency and token analysis |
| Semantic retrieval / RAG | Unit modelling, chunking, embeddings, vector search, metadata filters, aggregation to jobs, retrieval evaluation, stale indexes and re-indexing |
| SLMs, open-weight and closed-weight models | Local and hosted inference, structured outputs, bounded tasks, capability differences, quality/latency/cost trade-offs and stronger-model fallback |
| Agent architecture | Planning, tool selection, capability composition, evidence merging, grounded synthesis and separating deterministic logic from probabilistic reasoning |
| LLMOps | Model/prompt versions, token usage, latency, failures, retries, fallback rates and regression tests |
| Production engineering | Service boundaries, adapters, idempotency, versioned derived data, read-only safeguards, testability and migration to managed services |

Use these concepts when a real application requirement makes them useful. Do not add loops, parallelism or human approval solely to showcase a feature.

## Orchestration and state

Use LangGraph directly. Keep nodes small and testable, with explicit state transitions and dependencies.

State should make the request and inherited conversation scope, selected capabilities, tool inputs/results, source identifiers, evidence, failures, retry/fallback attempts and final answer inspectable. Choose an explicit persistence/checkpointing strategy when implementing conversational state.

The planner composes structured query, semantic retrieval and synthesis. There is no mandatory fixed structured/semantic/hybrid graph path. Independent retrieval may run in parallel; dependent operations run sequentially. Validate model-produced plans and structured outputs before tool execution.

SQL handles deterministic facts, filtering, joins, ranking and aggregation. Models handle interpretation, conceptual query formulation and grounded synthesis. Neither planning nor fallback may bypass deterministic safety checks.

See [retrieval_contract.md](retrieval_contract.md) for runtime behaviour, including conversational follow-ups, clarification, refusal and evidence discipline.

## External service boundaries

Use small ports and adapters around external infrastructure and models. Configuration selects implementations; graph nodes depend on interfaces rather than importing provider-specific clients.

| Boundary | Confirmed direction | Potential implementations or future substitutions |
|---|---|---|
| RelationalStore | SQLite initially | Postgres later |
| VectorStore | Provider not selected | Qdrant, pgvector, Pinecone or Azure AI Search |
| EmbeddingProvider | Provider/model not selected | Hosted or local embedding provider |
| ModelProvider | Providers/runtimes not selected | Hosted APIs, Ollama or vLLM |
| Observability/evaluation boundary | LangSmith | Narrow isolation where it helps testing |

Qdrant and Ollama are potential candidates, not selected defaults or dependencies. Assess the service requirements, local hardware and measured trade-offs before selecting implementations. LangGraph and LangSmith are deliberate learning choices; vector storage, local inference runtime and model selections remain open.

These are design directions, not a requirement to implement every adapter. Keep interfaces capability-oriented and introduce only methods that actual use cases need. Document capabilities that a replacement service cannot support; configuration changes alone do not guarantee backend equivalence.

Use LangGraph directly rather than wrapping it in a generic workflow framework. Use LangSmith directly enough to learn its traces, datasets and experiments. Infrastructure isolation must not hide the learning technologies.

SQLite is initially authoritative. Migration to another relational service is future work and must preserve domain/retrieval contracts while explicitly validating schema and SQL compatibility.

## Configuration and model strategies

Configure models through a configuration file with named profiles. Each profile assigns models independently by agent or model task, such as planning, SQL generation and synthesis. A single model may fill all roles, or different roles may use different models. These names describe configurable responsibilities; they do not require separate autonomous agents.

An illustrative configuration:

```yaml
models:
  local_candidate:
    provider: ollama  # Potential example only; runtime/provider not selected.
    model: chosen-local-model
  hosted_candidate:
    provider: hosted
    model: chosen-hosted-model
  stronger_fallback:
    provider: hosted
    model: chosen-stronger-model

profiles:
  hosted_baseline:
    assignments:
      planner: hosted_candidate
      sql_generation: hosted_candidate
      synthesis: hosted_candidate
  mixed_candidate:
    assignments:
      planner: local_candidate
      sql_generation: local_candidate
      synthesis: hosted_candidate
    fallbacks:
      planner: stronger_fallback
      sql_generation: stronger_fallback

active_profile: hosted_baseline
```

This specifies the intended configuration capability; provider names, model names and schema are illustrative until implementation. Infrastructure configuration for relational, vector and embedding providers is separate from generative model profiles. Credentials belong in environment variables or another secret mechanism, not committed profile files.

A small configuration loader/factory resolves each assignment through the ModelProvider boundary and injects the resulting model capability into the relevant node. Changing models for an already supported provider must require a configuration change, with no graph or business-logic edits. Adding a provider may require a new adapter. Model identity and provider-specific invocation details stay behind the adapter, while resolved provider/model and settings remain visible in LangSmith.

Validate profile names, assignments, provider availability and required capabilities such as tool use or structured outputs before execution. Unsupported configurations must fail explicitly; do not silently replace the selected model. Explicitly configured fallback must be visible and measurable. Keep invocation settings, prompt references, retry limits and fallback policy reproducible in the effective configuration.

Compare these strategies with the same evaluation dataset:

| Strategy | Assignment |
|---|---|
| A | Strong hosted model for all model tasks |
| B | Small/local model for planning; hosted model for synthesis |
| C | Small/local model for most tasks |
| D | Small/local model with stronger-model fallback |

Measure answer quality, capability/tool selection accuracy, latency, token usage, API cost where relevant and fallback rate. Record versions and configuration so comparisons are reproducible. Do not equate local inference with zero operating cost.

Start small models on bounded planning, classification, extraction or simple synthesis. Do not assign the hardest reasoning tasks to them merely to demonstrate local inference. Validate outputs, bound retries and fallback, and record failure categories and attempts.

## Model comparison and human selection

The evaluation harness must accept multiple named model profiles and run the same golden questions against each, using the same graph implementation. Make a comparison possible without editing nodes or copying evaluation code.

1. Build a versioned LangSmith dataset from the golden questions and executable fixtures, retaining question IDs. Include prior conversation for contextual cases and a fixed reference date for time-dependent cases.
2. Run each selected profile as a distinct LangSmith experiment. Fix the source-data snapshot, derived index, embedding configuration, prompts and evaluator versions when isolating model differences. Record any intentional differences as separate strategy experiments.
3. Record the effective profile, resolved models per agent/task, model settings, prompt/evaluator versions, data/index versions, retries and fallback policy. Configure any model-based evaluator independently from the models being tested.
4. Compare per-question, per-capability and overall quality, correctness, groundedness, evidence completeness, latency, tokens, cost where available and fallback rate. Inspect traces for failures. Distinguish the initial model's performance from success achieved through stronger-model fallback; include fallback overhead in end-to-end latency and cost.
5. Present results and trade-offs for human selection. The human chooses a complete profile or a combination of per-agent/task assignments. Evaluate a newly combined profile end to end before treating it as validated, then activate the chosen profile through configuration.

Model outputs can vary. Support repeated runs where that variation could change the selection, and report variability rather than treating one run as definitive. Use isolated task evaluations where useful to diagnose model suitability, alongside full-agent golden-question runs.

There is no automatic universal winner. Any quality threshold, cost ceiling or weighted selection rule must be explicitly chosen by the human. Passing existing behavioural and safety requirements remains a condition of a valid configuration.

During implementation, verify that switching profiles and changing a single role assignment do not require graph rewrites, invalid configurations fail clearly, and experiment metadata identifies the models actually used.

## Indexing boundary

Indexing is a separate process from read-only agent requests:

```text
Canonical relational data
  -> detect changed jobs and assessments
  -> build and normalize semantic units
  -> chunk long descriptions where appropriate
  -> compare content and configuration versions
  -> embed new/changed units
  -> activate replacements and deactivate obsolete units
```

Support idempotent replay, source and assessment updates, deletion/restoration, freshness checks, selective re-indexing and full rebuilds. Only the current successful assessment for each job contributes assessment units. Reassessment can change content while retaining the same assessment ID. Normal indexing deactivates obsolete records; inactive vectors remain excluded from search through `is_active = false`. No real-time CDC is required initially.

See [indexing.md](indexing.md) for unit granularity, identity, provenance and migration rules. See [data_semantics.md](data_semantics.md) for source meaning and deletion state.

## Read-only enforcement

Every source database access in the agent request path is read-only. Model-generated SQL is untrusted input.

Enforce access restrictions at the database boundary and validate statements deterministically. Write statements, write PRAGMAs and unauthorized multi-statement execution must fail regardless of prompts or model choice. Indexing writes target the derived index through a separate process.

## Evaluation and observability

Evaluation is part of the architecture from the start. Use LangSmith datasets, traces, evaluators and experiments while developing the first working flow.

The acceptance sources are:

- [../evals/golden_questions.yaml](../evals/golden_questions.yaml): user-facing capability and answer behaviour.
- [../evals/indexing_cases.yaml](../evals/indexing_cases.yaml): transformation and index correctness.

Create executable fixtures and evaluators during implementation. The YAML cases specify expectations; they are not evidence of passing executable tests.

Agent evaluation covers planning/capability selection, tool selection, SQL correctness, semantic relevance, evidence completeness, groundedness, answer quality, latency, token usage, retries and fallback.

Indexing evaluation covers unit generation, bullet/list parsing, chunk correctness, idempotency, freshness, source and assessment update propagation, deletion, schema/embedding version changes, stale-vector detection and rebuild correctness.

Trace task/model/provider and prompt versions, selected capabilities, tool execution, latency, token usage where available, retries, fallbacks, status and failure categories. Compare prompts and models through recorded experiments and regression evaluation.

Analytics over source `llm_calls` and tracing of this analytics agent are separate concerns. Do not write agent traces into the canonical source database from the request path.

## Initial scope

In scope:

- Read-only SQL analytics and semantic retrieval.
- Incremental semantic indexing and job-level evidence merging.
- Grounded synthesis and conversational follow-ups.
- LangGraph orchestration and LangSmith tracing/evaluation.
- SLM, open-weight and closed-weight model experiments and provider/model comparisons.
- Lightweight LLMOps and replaceable external services.

Out of scope initially:

- Modifying application data through the agent.
- Automatic job applications, CV generation and email/browser automation.
- Production authentication and full multi-tenancy.
- Kubernetes and large-scale distributed infrastructure.
- Real-time CDC.

## Decision principles and unresolved mappings

Prefer explicit architecture, deterministic safeguards, dependency injection, visible state and evaluation-driven development. Avoid hiding deterministic rules in prompts or over-engineering adapters before a second implementation is plausible.

Correctness, learning value, testability, service replaceability, a credible path to scale and simplicity are equally important criteria. There is no fixed priority order or default weighted score.

When a material conflict prevents satisfying them together, present feasible options with clear evidence, benefits, costs, risks and uncertainties. State which criteria each option improves or compromises, explain the recommendation, and let the human choose before implementing the disputed decision. Record the choice and its rationale. Continue independent preparation and routine work within the authorised scope while that decision is pending.

Equal importance does not make existing contracts optional. If an option requires changing a contract, identify the change explicitly and obtain the human's decision before implementing it. Do not silently trade away read-only safeguards or evidence requirements.

The checked Copilot source mapping, decision vocabularies, score scales, locations, current-assessment relationship and timestamps are documented in [data_semantics.md](data_semantics.md). Two integration facts remain explicit: the source lacks the target `is_deleted`/`deleted_at` fields and a native source-version counter. Resolve soft-deletion support before implementation; derive revision tokens without mutating the canonical source. Application closure and interview-stage semantics remain unnormalised free text. Define the source of the candidate technical profile for profile-similarity questions. Do not silently invent schema or profile facts.
