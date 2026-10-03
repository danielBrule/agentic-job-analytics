# Retrieval Contract

## Purpose

This document defines how the runtime job-analytics agent decides what information source to use and how retrieved evidence becomes an answer.

It describes behaviour, not implementation technology.

SQLite is the authoritative relational store. The vector database is a derived semantic index.

---

## 1. Capability composition

Compose reusable capabilities according to the information required:

- `structured_query`: authoritative relational retrieval and deterministic analysis.
- `semantic_retrieval`: conceptual evidence retrieval from the derived index.
- `synthesis`: grounded interpretation and evidence combination where needed.

Do not require every request to enter a rigid STRUCTURED, SEMANTIC or HYBRID route. These labels may describe a plan for tracing or evaluation, but do not determine a fixed graph path. The sections below describe retrieval needs rather than mutually exclusive execution routes.

Capabilities may execute independently, sequentially or in parallel. Choose the simplest correct plan based on constraints and dependencies. Clarification, out-of-scope handling and refusal are behaviours, not retrieval tools.

See [architecture.md](docs/architecture.md) for LangGraph state and provider boundaries.

---

## 2. Structured query capability

Use structured retrieval when the answer depends on explicit database values or deterministic relational operations.

Typical examples:

- exact company or job lookup
- dates
- countries or locations
- application status
- numeric scores
- counts
- averages
- grouping
- sorting
- threshold filters
- latest records
- joins
- exact stored text requested by identifier

Examples:

> How many jobs did I add each month by country?

> Which jobs have `tech_bar_fit >= 8` and `seniority_fit <= 5`?

> Show the decision reason for job 123.

### Rules

- Use SQL.
- SQL is read-only.
- Model-generated SQL is untrusted: enforce read-only restrictions deterministically with database access restrictions and SQL validation, including write PRAGMAs and multiple statements.
- Prefer SQL over Python for relational filtering, joins and aggregation.
- Do not invoke semantic retrieval when structured data answers the question exactly.
- LLM synthesis is optional and should only be used when interpretation is needed.

---

## 3. Semantic retrieval capability

Use semantic retrieval when the request depends on conceptual similarity or meaning rather than exact stored values.

Typical examples:

- roles similar to Forward Deployed Engineering
- mandates involving discovery-to-production ownership
- roles that are very hands-on with limited line management
- GenAI/agentic roles that are not research roles
- transformation-oriented Head of Data & AI roles

### Retrieval unit

Semantic search retrieves semantic units, not whole jobs.

A semantic unit can be:

- the complete `technical_bar` field or unmarked assessment text
- one bullet from `role_snapshot`, `real_mandate` or `decision_reason`
- one item from a list field
- one chunk of a job description

See `docs/indexing.md`.

### Flow

```text
user query
    ↓
semantic query formulation
    ↓
optional field / metadata filtering
    ↓
vector search
    ↓
top semantic units
    ↓
group by job_id
    ↓
retrieve authoritative parent context from SQLite
    ↓
synthesis
```

### Rules

- A semantic hit is evidence for a job, not the complete job.
- Always preserve the source `job_id`.
- Consolidate repeated hits from the same job before presenting results.
- Load parent context when a small semantic unit is insufficient to support the conclusion.
- Do not present vector metadata as canonical when SQLite contains the authoritative value.

---

## 4. Combining capabilities

Compose structured query and semantic retrieval when a question contains both structured constraints and semantic criteria.

Example:

> Which France-based roles similar to FDE have the strongest seniority fit?

Semantic component:

```text
similar to FDE
```

Structured components:

```text
location = France
seniority_fit
```

### Execution order

The contract does not require a universal fixed order.

Possible patterns include:

```text
structured filter → semantic search
semantic search → structured enrichment/filter
parallel retrieval → merge
structured seed set → semantic comparison
```

Choose the composition that is most selective, correct and simple for the case.

Where supported, push safe metadata filters into vector retrieval when doing so reduces the candidate set without changing semantics.

### Rules

- SQL remains authoritative for structured values.
- Vector similarity remains an intermediate semantic signal.
- Final answers operate at job level, not semantic-unit level.

---

## 5. OUT_OF_SCOPE

Use `OUT_OF_SCOPE` when the requested information cannot reasonably be derived from the available job-search data and the runtime agent has no authorised source for it.

Examples:

> What will the weather be tomorrow in Paris?

> What is the current unemployment rate in France?

The agent should explain briefly that the information is outside the available data scope.

### Must not

For an out-of-scope request:

- do not generate exploratory SQL hoping to find unrelated data
- do not perform vector search
- do not fabricate an answer from job-search content

---

## 6. REFUSAL

The runtime analytics agent is read-only.

Requests to modify canonical data are refused.

Example:

> Delete all rejected applications.

Must not:

- execute write SQL
- modify SQLite
- modify the vector index as a side effect of the user request

This is distinct from `OUT_OF_SCOPE`: the request may concern in-scope data but ask for an unauthorised action.

---

## 7. CLARIFICATION

Ask for clarification when the request is materially ambiguous and different interpretations would produce meaningfully different answers.

Example:

> What are the best roles?

Possible dimensions include:

- `fit_score`
- `priority_score`
- interview probability
- `seniority_fit`
- sustainability

Do not ask for clarification when a reasonable interpretation is already established by conversation context.

---

## 8. Conversation context

Follow-up requests may inherit scope from the preceding interaction.

Example:

> Which roles are most similar to FDE?

followed by:

> And only in France?

The second request should reuse the prior semantic scope and add the structured location constraint.

Do not require the user to restate the complete query when the context is unambiguous.

---

## 9. Field-aware semantic retrieval

Semantic retrieval may target specific fields when the question clearly maps to a documented concept.

### Role nature / mandate

Prefer evidence from:

- `job_description`
- `role_snapshot`
- `real_mandate`

### Positive fit

Prefer evidence from:

- `strong_fit_signals`
- `technical_bar`
- `evidence_anchors`

### Risks

Prefer evidence from:

- `red_flags`
- `sustainability_risks`
- `evidence_gaps`

### Decision explanation

Prefer evidence from:

- `decision_reason`
- `red_flags`
- `sustainability_risks`
- `strong_fit_signals`

These are retrieval hints, not rigid exclusions.

Field semantics are defined in `docs/data_semantics.md`.

---

## 10. Qualitative aggregation

Some questions concern repeated qualitative patterns rather than similarity to a single concept.

Examples:

> Which red flags recur most often?

> Which sustainability risks recur most often among jobs with fit_score >= 8?

Preferred pattern:

```text
SQL selects the relevant source rows
    ↓
parse/normalise list values
    ↓
deterministic counts where values are equivalent
    ↓
LLM synthesis/clustering only where semantic grouping is needed
```

Do not use vector similarity as a substitute for exact counting.

If semantically similar phrases are grouped, make clear that the grouping is interpretive rather than an exact stored-value count.

---

## 11. Semantic scope and job-level ranking

Fine-grained indexing means several top semantic units may belong to one job.

Therefore:

```text
top_k semantic units != top_k jobs
```

Retrieve enough semantic candidates to support job-level deduplication.

Initial job-level ranking may use a simple rule such as the best semantic-unit score per job.

More complex ranking may consider:

- best semantic score
- number of supporting hits
- field relevance
- structured scores
- reranker score

Do not introduce a composite ranking without evaluation evidence or an explicit rule.

---

## 12. Parent-context reconstruction

Retrieve-then-expand is the default pattern for small semantic units.

Example:

```text
semantic hit:
sustainability_risks = "Multiple concurrent client engagements"

job_id = 42
    ↓
load relevant SQLite context
    ↓
role_snapshot
real_mandate
red_flags
sustainability_risks
job metadata
```

The exact amount of parent context should be proportional to the question.

Do not automatically load every field for every hit.

---

## 13. Evidence discipline

When synthesising:

- distinguish retrieved evidence from inference
- do not strengthen a weak source statement into a strong conclusion
- use the canonical record for factual attributes
- use multiple supporting units when making broad claims
- surface important evidence gaps where they materially limit confidence

Example:

```text
"Some travel expected"
```

does not by itself justify:

```text
"The role has an unsustainable travel requirement."
```

---

## 14. Deleted and stale data

Normal retrieval excludes deleted jobs.

The vector index must apply:

```text
is_deleted = false
deleted_at IS NULL
```

by default.

Both deletion fields must be consistent with the canonical record. Conflicting state is an explicit error and must not allow a job into normal retrieval. See `docs/data_semantics.md`.

If vector content is stale relative to a newer SQLite source version or source timestamp, use the current SQLite record and do not present stale indexed text as current evidence.

---

## 15. Evaluation

User-facing retrieval capability is evaluated by:

```text
evals/golden_questions.yaml
```

That file is capability-based rather than route-implementation-based.

Changing the vector database, embedding model, chunk size, ANN algorithm or orchestration framework should not require changing golden questions unless desired user behaviour changes.

Index transformation behaviour is evaluated separately in:

```text
evals/indexing_cases.yaml
```


Use LangSmith traces, datasets, evaluators and experiments from the beginning. Measure planner/capability and tool selection, SQL correctness, semantic relevance, evidence completeness, groundedness, answer quality, latency, token usage, retries and fallback. Preserve the same user-facing questions across model/provider experiments; change them only when desired behaviour changes.

Retries and fallback must be bounded and visible. An invalid SQL statement, failed tool or unsupported model output is an explicit failure, not permission to relax safeguards or fabricate evidence.
