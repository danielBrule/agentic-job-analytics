# Retrieval Contract

## Purpose

This document defines how the runtime job-analytics agent decides what information source to use and how retrieved evidence becomes an answer.

It describes behaviour, not implementation technology.

Copilot SQLite is canonical. Runtime SQL and semantic retrieval use one published analytics SQLite snapshot/vector generation. SQLite in that pair is authoritative for its facts; the vector index is derived. Older but consistent data is acceptable. Each request pins the pair, and the capture time is visible. See [snapshot ingestion and publication](indexing.md#snapshot-ingestion-and-publication).

---

## 1. Capability composition

Compose reusable capabilities according to the information required:

- `structured_query`: authoritative relational retrieval and deterministic analysis.
- `semantic_retrieval`: conceptual evidence retrieval from the derived index.
- `synthesis`: grounded interpretation and evidence combination where needed.

Do not require every request to enter a rigid STRUCTURED, SEMANTIC or HYBRID route. These labels may describe a plan for tracing or evaluation, but do not determine a fixed graph path. The sections below describe retrieval needs rather than mutually exclusive execution routes.

Capabilities may execute independently, sequentially or in parallel. Choose the simplest correct plan based on constraints and dependencies. Clarification, out-of-scope handling and refusal are behaviours, not retrieval tools.

See [architecture.md](architecture.md) for LangGraph state and provider boundaries.

---

## Current assessment scope

Use zero or one current assessment per job for assessment-dependent analytics and reconstruction. In the checked source, successful reassessment updates the same row; only status `ASSESSED` supplies usable scores/conclusions. Preserve unassessed jobs in job-only queries and description-based semantic search. Do not join historical attempts as if they were extra current assessments.

The exact identifiers, status/decision values and source freshness mapping are defined in [data_semantics.md](data_semantics.md). If a successful assessment is stale relative to the current job inputs, expose that limitation when it affects the answer rather than presenting it as newly assessed.

LLM usage analysis may include all relevant historical call rows. Their model/prompt versions come from the calls themselves. Joining calls to assessments attaches current role classifications and must not be represented as historical assessment snapshots.

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

See [indexing.md](indexing.md#2-indexed-fields).

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
location = FR
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
- `technical_bar` as role-requirement context, not proof of candidate fit
- `evidence_anchors`, keeping candidate facts separate from support inferences

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

Field semantics are defined in [data_semantics.md](data_semantics.md).

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

All SQL reads, vector membership, filters and parent reconstruction for a request use the same published `generation_id`. Reject a mismatched pair with `generation_mismatch`; do not silently mix a live source, candidate snapshot or another vector generation. A publication during execution does not change the pair pinned by that request.

Default vector retrieval selects current membership in the pinned generation and `is_active = true`. Reject hits whose parent job is absent from that SQLite snapshot. Assessment-derived hits require the referenced current assessment in the snapshot to remain usable (`ASSESSED`); description hits do not require an assessment. [Physical deletion](data_semantics.md#is_deleted-and-deleted_at) is reflected at successful publication, not by checking live Copilot during each request.

Validate evidence against the pinned SQLite content, source projections, hashes and expected unit membership. Opaque source revision tokens are compared for equality, not ordered; whole-second timestamps alone cannot establish content equality. A vector that disagrees with the pinned snapshot cannot establish a semantic match. Report the consistency failure rather than publishing partial results as valid evidence; runtime tools cannot repair the index.

Changes in live Copilot after capture do not invalidate the published pair. Report its capture time; do not claim it reflects current live data. A retained assessment may nevertheless be stale relative to job inputs within the snapshot; expose that distinct limitation when relevant. Before the first publication, report data unavailable. Failed ingestion leaves the previous consistent pair available.

---

## 15. Evaluation

[Golden questions](../evals/golden_questions.yaml) define user-facing capability and answer acceptance. [Indexing cases](../evals/indexing_cases.yaml) define transformation acceptance. Internal provider, model or indexing changes do not justify changing golden questions unless desired user behaviour changes.

Use the LangSmith [comparison workflow](architecture.md#model-comparison-and-human-selection), metrics and observability requirements in [architecture.md](architecture.md#evaluation-and-observability). Fixture readiness and reviewed labels are tracked in the [fixture guide](../evals/fixtures/README.md).

Retries and fallback must be bounded and visible. An invalid SQL statement, failed tool or unsupported model output is an explicit failure, not permission to relax safeguards or fabricate evidence.
