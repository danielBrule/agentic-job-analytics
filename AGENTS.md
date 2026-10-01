# Repository Agent Instructions

## Purpose

This repository implements an agent for analysing a structured job-search database.

These instructions govern how a coding agent should work on the repository. They are not the runtime prompt for the job-search agent.

Authoritative behavioural and data contracts live in:

- `docs/retrieval_contract.md` — runtime retrieval and answer behaviour
- `docs/data_semantics.md` — meaning of tables and fields
- `docs/indexing.md` — SQLite-to-vector indexing design
- `evals/golden_questions.yaml` — retrieval/answer acceptance cases
- `evals/indexing_cases.yaml` — indexing acceptance cases

If implementation and documentation disagree, do not silently choose one. Identify the conflict and resolve it explicitly.

---

## 1. Engineering principles

- Prefer the simplest implementation that satisfies the contracts and tests.
- Keep SQLite as the canonical source of truth.
- Treat the vector index as derived, disposable and rebuildable.
- Keep relational logic in SQL when SQL expresses it clearly.
- Use Python for orchestration, transformation, retrieval logic and application code.
- Do not duplicate canonical business state in the vector store.
- Do not introduce abstractions, frameworks or dependencies without a concrete need.
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

---

## 5. Read-only runtime agent

The runtime analytics agent is read-only.

Generated SQL must not:

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `CREATE`
- perform write PRAGMAs
- modify the vector index

Indexing jobs are separate implementation processes and may update the derived vector index.

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

Runtime retrieval must follow `docs/retrieval_contract.md`.

The top-level request classification is:

- `STRUCTURED`
- `SEMANTIC`
- `HYBRID`
- `OUT_OF_SCOPE`

`CLARIFICATION` and `REFUSAL` are behaviours, not additional data-retrieval routes.

Do not force every request through the vector index.

Do not approximate semantic retrieval with large collections of SQL `LIKE` clauses unless literal text search is explicitly intended.

---

## 8. Indexing implementation

Indexing must follow `docs/indexing.md` and `indexing_cases.yaml`.

Current semantic-unit policy:

- scalar assessment field → one vector
- list assessment field → one vector per meaningful list item
- `job_description` → multiple chunks when required

Indexing must be:

- incremental
- idempotent
- version-aware
- deletion-aware

Do not re-embed unchanged semantic units.

---

## 9. Data semantics

Before using a field in retrieval, ranking or synthesis, read `docs/data_semantics.md`.

Do not infer semantics from a field name alone when the field is documented.

Important distinctions include:

- `red_flags` vs `sustainability_risks`
- `role_snapshot` vs `real_mandate`
- `technical_bar` vs `tech_bar_fit`
- source evidence vs assessment conclusions

If the physical schema contains conflicting names or undocumented fields, inspect the schema and flag the discrepancy rather than guessing.

---

## 10. Dependencies

Before adding a dependency:

1. Check whether the standard library or an existing dependency is sufficient.
2. Explain why the dependency is needed.
3. Prefer mature, narrowly scoped libraries.
4. Avoid introducing infrastructure-specific coupling into domain contracts.

A change of vector database, embedding provider or orchestration framework should not require rewriting the retrieval or data-semantic contracts.

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

Do not silently swallow retrieval, parsing or indexing failures.

---

## 12. Documentation discipline

Update the relevant documentation when a contract changes.

Use:

- `README.md` for project overview only
- `AGENTS.md` for coding-agent working instructions
- `docs/data_semantics.md` for domain/data meaning
- `docs/retrieval_contract.md` for runtime behaviour
- `docs/indexing.md` for indexing architecture

Avoid duplicating detailed contracts across files.

Prefer links to the authoritative document instead.

## Related systems

This repository may reuse data produced by the CV Generation Copilot.

Authoritative data model:
`https://github.com/danielBrule/job-application-copilot/blob/main/docs/data-model.md`

When consuming Copilot data:
- treat its documented schema as authoritative
- do not duplicate or redefine shared field semantics here
- flag incompatible schema changes before implementation