# Repository Agent Instructions

## Purpose

This repository has two equally important objectives:

1. Build a credible, production-minded agentic analytics system over job-application data.
2. Use that system as a hands-on learning vehicle for modern agentic AI engineering.

Make state transitions, evidence flow and measured trade-offs understandable. A working application alone does not fulfil the learning objective.

The two primary learning goals are equally important:

- **LangGraph and LangSmith:** orchestration, state, tool execution, conversational persistence, tracing, datasets, evaluators and experiments.
- **Small language models (SLMs), open-weight and closed-weight models:** bounded task assignment, structured outputs, capability differences, provider/model comparison and stronger-model fallback.

Treat model size, weight accessibility and deployment location as separate dimensions. Open-weight does not necessarily mean small or local, and hosted does not necessarily mean closed-weight. Compare strategies using evidence rather than assuming one category is preferable.

Architecture, learning objectives, model experiments and initial scope are defined in [docs/architecture.md](docs/architecture.md).

These instructions govern how a coding agent should work on the repository. They are not the runtime prompt for the job-search agent.

Authoritative behavioural and data contracts live in:

- [docs/retrieval_contract.md](docs/retrieval_contract.md) — runtime retrieval and answer behaviour
- [docs/data_semantics.md](docs/data_semantics.md) — meaning of tables and fields
- [docs/indexing.md](docs/indexing.md) — SQLite-to-vector indexing design
- [evals/golden_questions.yaml](evals/golden_questions.yaml) — retrieval/answer acceptance cases
- [evals/indexing_cases.yaml](evals/indexing_cases.yaml) — indexing acceptance cases

Read and follow [SECURITY.md](SECURITY.md) when changing data handling, external-provider calls, tracing, logging, evaluation datasets, persistence or secrets management.

If implementation and documentation disagree, do not silently choose one. Identify the conflict and resolve it explicitly.

---

## 1. Engineering principles

- Do not agree by default. Assess proposals against the contracts, evidence and project objectives. Challenge assumptions when there is a concrete concern, explain the consequences and suggest alternatives. Agree when the reasoning supports agreement.
- Prefer the simplest implementation that satisfies the contracts, tests and learning objectives.
- Treat correctness, learning value, testability, service replaceability, a credible path to scale and simplicity as equally important architectural criteria, with no fixed priority order.
- When a material conflict prevents satisfying these criteria together, give the human a clear comparison of feasible options, supporting evidence, benefits, costs, risks and uncertainties. Explain the recommendation, then let the human choose before implementing the disputed decision. Do not silently impose a priority or scoring weight.
- Continue routine work and independent preparation within the already authorised scope. Escalate material unresolved trade-offs, not every implementation choice. Existing contracts remain requirements unless the human explicitly authorises changing them.
- Use LangGraph directly for orchestration and LangSmith directly for tracing and evaluation.
- Isolate external infrastructure and model services behind small explicit interfaces; keep provider-specific clients out of graph nodes.
- Do not hide LangGraph behind a generic workflow framework or force graph features without a real use case.
- Keep SQLite as the canonical source of truth.
- Treat the vector index as derived, disposable and rebuildable.
- Keep relational logic in SQL when SQL expresses it clearly.
- Use Python for orchestration, transformation, retrieval logic and application code.
- Do not duplicate canonical business state in the vector store.
- Treat service isolation, realistic substitution and testability as concrete reasons for small adapters. Avoid speculative interfaces or implementing every possible backend.
- Preserve clear boundaries between source data, indexing, retrieval, synthesis and evaluation.

---

## 2. Implementation workflow

For non-trivial changes:

1. Inspect the relevant code, schema, documentation and tests.
2. Identify which contract is affected:
   - data semantics
   - indexing
   - retrieval
   - public interface
   - persistence/schema
3. Propose a short implementation plan.
4. Get human confirmation before implementation when the change affects:
   - architecture
   - database schema
   - indexing granularity or identity
   - retrieval routing or ranking
   - public interfaces
   - external dependencies
   - evaluation contracts
5. Write or update tests before implementing the behaviour.
6. Implement the smallest change that makes the tests pass.
7. Run targeted tests.
8. Run the broader relevant test suite.
9. Report:
   - what changed
   - tests run
   - important design decisions
   - remaining limitations or follow-up work

Small local fixes that do not change behaviour or contracts do not require an approval pause.

Use `dev.ps1` as the shared local/CI validation entry point. Run `./dev.ps1 check` before reporting a change complete; available targets and baseline scope are defined in [docs/development.md](docs/development.md).

---

## 3. Test-first default

For behavioural changes, tests come before implementation.

Examples:

- new indexing behaviour → add/update `indexing_cases.yaml` and executable tests first
- new retrieval behaviour → add/update `golden_questions.yaml` only if desired user-facing capability changes
- bug fix → reproduce the bug with a failing test first
- schema transformation → test migration/compatibility behaviour first

Do not modify golden questions merely to make an implementation pass.

The evaluation contract represents desired behaviour, not the current implementation.

---

## 4. Language and tool defaults

### Python

Use Python by default for:

- orchestration
- ETL/indexing logic
- parsing and normalisation
- retrieval coordination
- application services
- evaluation harnesses

Prefer:

- type hints
- small focused functions
- explicit data structures
- deterministic transformations
- standard library where sufficient

### SQL

Use SQL by default for:

- exact filtering
- joins
- aggregation
- ranking over structured values
- date filtering
- counts
- canonical record retrieval

Do not move deterministic relational operations into Python without a clear reason.

### LLMs

Use an LLM only where meaning, interpretation or synthesis is required.

Do not use an LLM for deterministic calculations, exact filters, simple joins or parsing that can be implemented reliably without one.

### Model configuration and comparison

Model selection must be configuration-driven through the `ModelProvider` boundary. Graph nodes and business logic must not hard-code model names or instantiate provider-specific clients. Support named model profiles with independent assignments by agent or model task, including fallback where configured.

Follow the [model comparison and human selection workflow](docs/architecture.md#model-comparison-and-human-selection). The human chooses profiles or per-agent/task assignments from comparable LangSmith experiments, then applies the selection through configuration. Keep resolved models visible in traces and out of business logic; do not invent a universal best model.

---

## 5. Read-only runtime agent

The runtime analytics agent and its tools are read-only.

SQL generated for the runtime request path must not:

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `CREATE`
- perform write PRAGMAs
- modify the vector index

Model-generated SQL is untrusted input. Enforce read-only access deterministically through database access restrictions and SQL validation; prompts alone are insufficient.

A separate indexing process may use deterministic SQL to read and identify changes in canonical SQLite data, then update the derived vector index through the approved indexing adapters. Python coordinates semantic-unit transformation, hashing, embedding and index lifecycle handling. If the approved vector backend supports SQL, its adapter may use SQL for derived-index writes.

These updates must follow [docs/indexing.md](docs/indexing.md) and must not modify canonical source data. The runtime agent cannot invoke indexing writes.

---

## 6. Source-of-truth rules

SQLite is authoritative for canonical application and assessment data.

The vector index:

- contains derived semantic units
- must preserve source identifiers
- may contain redundant metadata for filtering
- must never become the only copy of business information
- must be rebuildable from SQLite

When vector content conflicts with a newer SQLite record, SQLite wins.

---

## 7. Retrieval implementation

Runtime retrieval must follow [docs/retrieval_contract.md](docs/retrieval_contract.md).

Compose reusable capabilities: `structured_query`, `semantic_retrieval` and `synthesis`.

Do not impose rigid STRUCTURED / SEMANTIC / HYBRID execution routes. Capabilities may run independently, sequentially or in parallel according to the question. Labels may describe a plan for observability but must not constrain execution.

Clarification, out-of-scope handling and refusal remain explicit behaviours.

Do not force every request through the vector index.

Do not approximate semantic retrieval with large collections of SQL `LIKE` clauses unless literal text search is explicitly intended.

---

## 8. Indexing implementation

Indexing must follow `docs/indexing.md` and `evals/indexing_cases.yaml`.

The indexing contract owns unit granularity, parsing, identity, versioning and lifecycle rules. Keep indexing incremental and idempotent; re-embed only changed units in the affected job/field.

Use only the current successful assessment for assessment units, while keeping descriptions searchable without an assessment. Deactivate obsolete records and exclude them from normal search.

Preserve and propagate both `is_deleted` and `deleted_at` when supplied by the agreed source integration. Their absence in the checked source must remain explicit; follow [data semantics](docs/data_semantics.md#is_deleted-and-deleted_at) rather than querying absent columns.

---

## 9. Data semantics

Before using a field in retrieval, ranking or synthesis, read `docs/data_semantics.md`.

Do not infer semantics from a field name alone when the field is documented.

Important distinctions include:

- `red_flags` vs `sustainability_risks`
- `role_snapshot` vs `real_mandate`
- `technical_bar` vs `tech_bar_fit`
- source evidence vs assessment conclusions

Use the verified Copilot mapping in `docs/data_semantics.md`: human `jobs.user_decision` and model `assessments.decision` are distinct; evidence anchors are JSON objects. The source has no target soft-deletion fields or native source-version counter. Keep those gaps explicit and do not query absent columns or silently migrate the source.

If the physical schema contains conflicting names or undocumented fields, inspect the schema and flag the discrepancy rather than guessing.

---

## 10. Dependencies

Before adding a dependency:

1. Check whether the standard library or an existing dependency is sufficient.
2. Explain why the dependency is needed.
3. Prefer mature, narrowly scoped libraries.
4. Avoid introducing infrastructure-specific coupling into domain contracts.

A change of vector database, embedding provider or orchestration framework should not require rewriting the retrieval or data-semantic contracts. Qdrant and Ollama remain potential candidates, not selected dependencies.

---

## 11. Error handling and observability

Failures should be explicit and classifiable.

Prefer structured error categories over free-text-only errors.

For LLM and retrieval operations, preserve enough metadata to diagnose:

- operation
- pipeline step
- model
- latency
- token usage where applicable
- retry number
- status
- failure category
- selected capabilities and tools
- prompt/model versions
- fallback attempts and outcomes

Use LangSmith datasets, traces, evaluators and experiments from the start. Evaluate model strategies without rewriting the graph. Distinguish analytics over source `llm_calls` from tracing this analytics agent.

Do not silently swallow retrieval, parsing or indexing failures.

---

## 12. Documentation discipline

Update the relevant documentation when a contract changes.

Use:

- `README.md` for project overview only
- `SECURITY.md` for security/privacy requirements, boundaries and vulnerability reporting
- `AGENTS.md` for coding-agent working instructions
- `docs/data_semantics.md` for domain/data meaning
- `docs/retrieval_contract.md` for runtime behaviour
- `docs/indexing.md` for indexing architecture
- `docs/architecture.md` for learning objectives, orchestration, provider boundaries, model experiments and initial scope
- `docs/development.md` for setup, development commands, branch flow and CI operation

Avoid duplicating detailed contracts across files.

Prefer links to the authoritative document instead.

### Code comments and docstrings

Keep comments clear, concise and proportionate to the code:

- Give classes a short docstring explaining their purpose or responsibility.
- Document functions and methods when behaviour is non-obvious, including relevant assumptions, side effects, invariants or surprising return/error behaviour. Simple, self-explanatory helpers do not need a docstring.
- Use inline comments to explain why a choice is necessary or clarify a subtle step; avoid narrating obvious operations or repeating names and type hints.
- Expand explanations only where complexity or the learning objectives justify them; keep detailed architecture and contracts in their authoritative documents.
- Update or remove comments when the code changes so they remain accurate.

## Related systems

This repository may reuse data produced by the CV Generation Copilot.

The [verified source mapping](docs/data_semantics.md#verified-copilot-source-mapping) links the authoritative upstream data model and code at the checked revision.

When consuming Copilot data:
- treat its documented schema as authoritative
- do not duplicate or redefine shared field semantics here
- flag incompatible schema changes before implementation
