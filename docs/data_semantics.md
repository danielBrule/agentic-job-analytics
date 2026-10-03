# Data Semantics

## Purpose

This document defines the business meaning of the data used by the job-analytics agent.

It is a semantic contract, not database DDL.

Before changing queries or retrieval logic, inspect the physical SQLite schema and reconcile any differences with this document rather than assuming column names or types.

---

## Verified Copilot source mapping

The authoritative shared schema and field definitions are [Copilot's data model](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/docs/data-model.md). This integration was checked against code at commit `58c46bbfbed41d469b139cf5db054f7002582085`. The notes below specify analytics use and mapping; they do not redefine Copilot business semantics.

| Analytics identifier or concept | Physical source |
|---|---|
| `job_id` | `jobs.id`; referenced by `assessments.job_id` and `llm_calls.job_id` |
| `assessment_id` | `assessments.id` |
| Human application decision | `jobs.user_decision` |
| Model recommendation | `assessments.decision` |
| Job source update | `jobs.updated_at` |
| Assessment source update | `assessments.updated_at` |
| Inputs used for the assessment | `assessments.source_job_updated_at` |
| Current assessment-input revision | `jobs.assessment_input_updated_at` |
| Current assessment prompt version | `assessments.prompt_version` |
| Historical call prompt version | `llm_calls.version_metadata["prompt_version"]` |

Job and assessment row timestamps use UTC without a timezone suffix and with whole-second precision. Interpret them as UTC, not workstation-local time. Timestamps are change-detection hints, not unique version counters; content hashes must detect semantic changes even when timestamps match.

The checked source has no native `source_version`, `is_deleted` or `deleted_at` columns. `source_version` in the derived index is an opaque revision token computed from a deterministic source projection, not an assumed integer source column. Keep the two deletion fields as target requirements and resolve the source integration before relying on them.

Evidence: [job model](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/src/job_application_copilot/repositories/models/job.py), [assessment model](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/src/job_application_copilot/repositories/models/assessment.py), [assessment persistence](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/src/job_application_copilot/services/assessment_persistence.py), [assessment domain](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/src/job_application_copilot/domain/assessment.py), [job domain](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/src/job_application_copilot/domain/job.py), [call recording](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/src/job_application_copilot/services/assessment_execution.py).

---

## 1. Core entities

The current evaluation contract references three main logical tables:

```text
jobs
assessments
llm_calls
```

### `jobs`

Represents a job opportunity/application and its source job information.

### `assessments`

Represents the interpreted assessment of a job, including role characterisation, fit, risks and decision rationale.

### `llm_calls`

Represents observability records for LLM operations used by the application.

---

## 2. `jobs` semantics

### `job_id`

Stable identifier for a job: physical `jobs.id`, exposed as `job_id` in semantic units.

Used as the main join and reconstruction key across relational and semantic retrieval.

### `company`

Employer/company associated with the role.

Use for exact structured filtering and display.

### `job_title`

Advertised role title.

This is source metadata. It should not be treated as a complete description of the actual mandate.

### `location`

Stored location for the job.

Use structured filtering for exact country constraints. This field does not encode a city.

The checked source stores the enum values `UK`, `FR` and `CH`. Use `FR` for France; do not infer countries from free-text city matching.

### `date_added`

Date the job was added to the system.

Used for time-series and period filtering.

### `application_status`

Current application/process status.

The checked source stores free text, not a controlled status enum. Do not invent a canonical interview/closed vocabulary; define and evaluate any normalization explicitly before using it for those questions.

### `next_action`

Next expected application action.

### `next_action_date`

Date associated with `next_action`.

### `closure_reason`

Reason an application is closed.

The exact definition of "closed" should eventually be normalised rather than inferred from missing/non-missing text.

### `job_description`

Original or captured long-form description of the role.

Semantics:

- source evidence
- not an assessment conclusion
- may contain marketing language, duplicated sections and generic company content
- useful for semantic retrieval
- chunked in the vector index

Do not overwrite the job description with assessment-generated summaries.

### `is_deleted` and `deleted_at`

Both fields are required by the target deletion contract:

- `is_deleted` indicates the current soft-deletion state.
- `deleted_at` records when the current deletion occurred, as an unambiguous timestamp.
- Active or restored jobs have `is_deleted = false` and `deleted_at = null`.
- Deleted jobs have `is_deleted = true` and a non-null `deleted_at`.

Deleted jobs are excluded from normal retrieval. Indexing propagates both values to all units for the job. Inconsistent values produce an explicit `inconsistent_deletion_state` error and exclude the job from normal retrieval; do not silently repair canonical data.

The checked Copilot model has neither field; its job service performs physical deletion. This is an explicit source-integration gap. Keep both fields as target requirements, but do not generate SQL against absent columns, infer deletion from application closure, or modify the source from this agent. Resolve the upstream schema/adapter strategy before implementing soft-deletion support.

For a job confirmed missing from a complete source snapshot, deactivate its derived units and classify it as `source_record_missing`. Do not invent a canonical deletion timestamp. A failed or partial source read is not evidence of deletion.

### Source freshness

The mapping above identifies canonical update timestamps. They are synchronization hints; administrative edits do not imply semantic changes. Derived revision tokens, content hashes and index synchronization timestamps are defined in [indexing provenance](indexing.md#provenance-naming). Assessment-input staleness is defined separately below.

---

## 3. `assessments` semantics

### Current assessment relationship

For normal analytics and indexing:

```text
one job -> zero or one current assessment
```

The upstream database enforces a unique `assessments.job_id`. Successful reassessment updates the existing row, preserving its ID; it does not append another assessment. A failed reassessment preserves the previous successful row. Therefore "last assessment" means the latest successful result retained in that current row, not the last attempted call.

Rows may have `PENDING`, `RUNNING`, `ASSESSED` or `FAILED` status. Only `ASSESSED` supplies usable assessment conclusions, scores and semantic units. A job with no usable assessment still participates in job-only questions and job-description retrieval. Do not fabricate an assessment or treat a pending/failed row as a zero score.

Use a left join when the question includes unassessed jobs; require `ASSESSED` when the question depends on assessment values. Detect multiple current rows as a source-schema violation instead of multiplying counts or choosing one arbitrarily.

A retained successful assessment may be stale after a relevant job edit. Compare `assessments.source_job_updated_at` with `jobs.assessment_input_updated_at` and make staleness explicit when it affects the answer. This is separate from vector-index staleness. Administrative edits do not automatically invalidate the assessment.

`llm_calls` retains individual historical invocations and can contain many rows per job. Do not interpret those rows as historical assessment records. Joining them to assessments provides the current role classification, not the classification at the time of each call.

### `assessment_id`

Stable identifier for the current assessment: physical `assessments.id`, exposed as `assessment_id` in semantic units.

Semantic units derived from assessment fields should retain this identifier.

### `job_id`

Links the assessment back to its job.

### `role_snapshot`

Concise interpretation of what the role is overall.

Use it to capture the role shape at a higher level than the raw title.

Typical content may include:

- seniority/role shape
- delivery vs strategy balance
- leadership vs individual contribution
- client-facing vs internal orientation
- broad technical/business positioning

It is an assessment summary, not source evidence.

Stored as scalar text, usually formatted with bullets. Its searchable representation is defined in [indexing.md](indexing.md#bullet-formatted-assessment-text).

### `real_mandate`

Interpretation of what the person would actually be expected to accomplish.

This may differ from the advertised title or wording.

Stored as scalar text, usually formatted with bullets.

Typical content may include:

- build a capability
- lead first client deployments
- scale a team
- own discovery through production
- drive commercial growth
- transform an operating model

Distinction:

```text
role_snapshot = what kind of role this is
real_mandate  = what the person is really expected to deliver
```

### `technical_bar`

Description of the technical capability expected by the role.

This describes the role requirement, not the candidate's score against it.

Do not confuse with `tech_bar_fit`, which is a structured assessment of fit against that bar.

### `decision_reason`

Explanation supporting the model recommendation in `assessments.decision`. It does not explain the human decision in `jobs.user_decision`.

This is interpretive and may combine fit, seniority, mandate, risks, commercial considerations, sustainability and evidence gaps.

Do not treat it as raw job-description evidence.

Stored as scalar text, usually formatted with bullets.

---

## 4. List-valued assessment fields

The following fields are stored as JSON arrays and should be parsed before processing. The first four contain strings; `evidence_anchors` contains objects:

```text
strong_fit_signals
red_flags
sustainability_risks
evidence_gaps
evidence_anchors
```

Storage and searchable representations are distinct; [indexing.md](indexing.md#list-semantic-fields) defines the projection.

### `strong_fit_signals`

Positive evidence indicating why the role aligns with the candidate/profile being assessed.

Examples of concepts:

- relevant technical experience
- team-building experience
- consulting/delivery experience
- domain match
- end-to-end ownership match

This is assessment evidence, not a general list of attractive job characteristics.

### `red_flags`

Broad concerns that may make the role less suitable, attractive or credible.

Possible concepts:

- excessive commercial responsibility
- mismatch in seniority
- unclear scope
- weak technical content
- organisational concerns
- unexpected stakeholder model

`red_flags` is broader than sustainability.

A red flag can exist even if the role would be sustainable.

### `sustainability_risks`

Factors that may make the role difficult to sustain over time.

Typical concepts:

- excessive workload
- travel
- long hours
- too many concurrent engagements
- constant executive/client interaction
- unclear boundaries
- operational intensity

Distinction:

```text
red_flags
    broad concerns about suitability / attractiveness

sustainability_risks
    concerns specifically about maintaining the role over time
```

### `evidence_gaps`

Missing or ambiguous evidence relevant to the assessment, including gaps in the documented candidate profile against the role requirements. Identify whether a gap concerns candidate evidence or missing role information; do not assume all gaps describe missing job-description details.

Examples:

- no documented experience in the employer’s industry
- unclear evidence of candidate ownership at the required scope
- unclear role expectations that prevent assessing the match

The checked upstream [assessment fixture](https://github.com/danielBrule/job-application-copilot/blob/58c46bbfbed41d469b139cf5db054f7002582085/tests/fixtures/assessment_output_valid.json) includes a candidate industry-experience gap.

An evidence gap should reduce confidence. It should not be silently converted into either a positive or negative fact.

### `evidence_anchors`

In the checked source this is a JSON array of objects, not strings. Each object contains `source_reference`, `evidence` and `supports`. It records a traceable Document A candidate-profile fact and the assessment inference that fact supports. Do not present it as a verbatim job-description excerpt.

Keep each anchor traceable to its assessment/job and source reference. The canonical object stays in SQLite; [indexing.md](indexing.md#evidence-anchor-objects) defines deterministic rendering and identity.

---

## 5. Role-family fields

### `primary_role_family`

Primary classification of the role, stored as an installation-specific configured lane ID.

Used for structured grouping/analytics.

### `secondary_role_family`

Secondary classification where a role spans more than one family.

Role-family identifiers use the configured lane vocabulary from the upstream validated routing set; they are not a universal enum. Labels are explicit classifications and should not automatically replace semantic similarity search.

For example, a query for roles "similar to Forward Deployed Engineering" may use semantic evidence even when role-family labels are available.

---

## 6. Structured fit and priority fields

The evaluation contract references:

```text
fit_score
priority_score
tech_bar_fit
seniority_fit
```

These are structured numeric assessment dimensions.

### `fit_score`

Overall assessed fit.

### `priority_score`

Priority assigned to the opportunity.

Do not assume it is interchangeable with `fit_score`; priority may incorporate factors beyond fit.

### `tech_bar_fit`

Assessment of how well the candidate/profile matches the role's technical bar.

Distinct from `technical_bar`, which describes the bar itself.

### `seniority_fit`

Assessment of seniority alignment.

Do not infer seniority fit solely from title when this structured field is available.

### Scale

The source domain validates integer scores from 0 to 10, including fit, priority, technical-bar fit and seniority fit. Missing values in incomplete assessments mean unavailable, not zero. Interview-probability bounds/confidence and evidence confidence also use this scale.

---

## 7. Decision fields

These are distinct source concepts, not aliases:

| Field | Meaning | Stored values |
|---|---|---|
| `jobs.user_decision` | Human decision to pursue the opportunity | `UNDECIDED`, `PURSUE`, `DO_NOT_PURSUE` |
| `assessments.decision` | Model assessment recommendation | `GO`, `CAUTION`, `STRETCH`, `NO_GO` |

Use the human field for "I decided not to pursue" and the assessment field for "classified GO/NO_GO". Display labels in upstream documentation/UI may differ in capitalization and punctuation from stored enum values. Preserve the stored values in exact filters.

---

## 8. `material_mandate_dimensions`

The source stores a JSON array of structured objects with `id`, `description`, `importance`, `evidence_strength`, `evidence_anchor_refs`, `should_shape_cv` and `support_categories`.

Parse it deterministically before qualitative synthesis. `importance` uses 0–10; `evidence_strength` is `DIRECT`, `ADJACENT`, `WEAK` or `NONE`. The upstream domain contract defines the support-category vocabulary and validates evidence references. Follow it rather than inferring meaning from object key names.

The field remains available for structured/qualitative analytics. It has no semantic-indexing policy unless explicitly added to that contract. CV-related annotations do not bring CV generation into this project's scope.

---

## 9. Source evidence vs assessment interpretation

Keep this distinction explicit.

### Source evidence

Primarily:

```text
job_description
```

and external/source-derived factual job metadata. `evidence_anchors[].evidence` records candidate-profile facts from Document A, a separate source from the job description. An anchor's `supports` statement is an assessment inference.

### Assessment interpretation

Includes:

```text
role_snapshot
real_mandate
technical_bar
decision_reason
strong_fit_signals
red_flags
sustainability_risks
evidence_gaps
evidence_anchors[].supports
fit_score
priority_score
tech_bar_fit
seniority_fit
role families
```

When answering, do not present an assessment inference as though it were explicitly stated in the source job description.

---

## 10. `llm_calls` semantics

The evaluation contract references:

```text
operation
resolved_model
total_tokens
job_id
pipeline_step
duration_seconds
retry_number
status
failure_category
version_metadata
```

### `operation`

Logical operation performed by the LLM call.

Example evaluation value:

```text
ASSESSMENT
```

### `resolved_model`

Actual model used after configuration/routing resolution. It is nullable; retain an explicit unresolved category rather than inventing a model. `requested_model` and `provider` are available separately.

### `total_tokens`

Total token usage reported for the call. `NULL` means unreported; zero means explicitly reported as zero. Include reported usage from failed calls as well as successes and report missing-usage coverage. Do not add cache-read/write counts again to `total_tokens`.

### `pipeline_step`

Logical step within a larger workflow.

### `duration_seconds`

Observed duration of the call/step.

### `retry_number`

Retry attempt number.

### `status`

Stored call outcomes are `SUCCEEDED` and `FAILED`, distinct from assessment-row statuses.

### `failure_category`

Normalised category for failure analysis.

Prefer categories over relying only on free-text exception messages.

### `task_id` and `task_attempt_id`

Nullable identifiers for the source background task and its execution attempt. A task can produce multiple calls, steps and retries. These identifiers can support run-level accounting, but the evaluation definition of “per assessment” is unresolved. Do not combine unrelated calls with missing task IDs into one invented assessment run.

### `version_metadata`

Version information associated with the call.

For historical assessment calls, extract `prompt_version` from `llm_calls.version_metadata`; `assessments.prompt_version` describes only the current result. Compare historical versions from their own call records, never by copying the current assessment version onto all calls.

---

## 11. Null and missing values

A missing value means "not available", not false.

Important examples:

- missing travel information is not "no travel"
- missing sales target is not "no sales target"
- missing sustainability risk is not proof of sustainability
- missing evidence is not negative evidence

Retrieval and synthesis should preserve this distinction.

---

## 12. Unresolved integration and evaluation definitions

| Topic | Definition still needed | Affected capability |
|---|---|---|
| Soft deletion | An agreed upstream schema or adapter strategy supplying both target deletion fields; the checked source physically deletes jobs | Deletion/restoration integration |
| Application closure | Explicit mapping from free-text process state to closed/open; missing `closure_reason` alone is insufficient | q06 |
| Interview history | A supported definition/source for having had an interview; current free-text status does not guarantee historical stage information | q18 |
| Candidate technical profile | Canonical source and version of the profile used for similarity, beyond individual assessment anchors | q19 |
| Tokens per assessment | Whether the unit is a task, attempt or invocation, model attribution, retry inclusion and treatment of unreported usage | q21 |

Resolve these definitions before implementing or fully grading the affected capability. Do not silently infer them or change the golden questions to fit available data. The [fixture guide](../evals/fixtures/README.md#remaining-coverage-and-review) records snapshot coverage and outstanding review; [indexing.md](indexing.md) owns semantic-unit representation.
