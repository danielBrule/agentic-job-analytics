# Data Semantics

## Purpose

This document defines the business meaning of the data used by the job-analytics agent.

It is a semantic contract, not database DDL.

Before changing queries or retrieval logic, inspect the physical SQLite schema and reconcile any differences with this document rather than assuming column names or types.

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

Stable identifier for a job.

Used as the main join and reconstruction key across relational and semantic retrieval.

### `company`

Employer/company associated with the role.

Use for exact structured filtering and display.

### `job_title`

Advertised role title.

This is source metadata. It should not be treated as a complete description of the actual mandate.

### `location`

Stored location for the job.

Use structured filtering for exact country/city constraints.

The physical representation and normalisation rules should be verified in the schema before implementing country-level logic.

### `date_added`

Date the job was added to the system.

Used for time-series and period filtering.

### `application_status`

Current application/process status.

The exact status vocabulary should be treated as schema/domain data rather than inferred from free text where possible.

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

### `is_deleted`

Soft-deletion state where present.

Deleted jobs must be excluded from normal retrieval.

---

## 3. `assessments` semantics

### `assessment_id`

Stable identifier for an assessment where present.

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

### `real_mandate`

Interpretation of what the person would actually be expected to accomplish.

This may differ from the advertised title or wording.

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

Explanation supporting the assessment/application decision.

This is interpretive and may combine fit, seniority, mandate, risks, commercial considerations, sustainability and evidence gaps.

Do not treat it as raw job-description evidence.

---

## 4. List-valued assessment fields

The following fields are stored as serialized string lists and should be parsed as lists before processing:

```text
strong_fit_signals
red_flags
sustainability_risks
evidence_gaps
evidence_anchors
```

Each meaningful item is independently indexed semantically.

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

Important information missing or ambiguous in the available evidence.

Examples:

- unclear team size
- unclear travel requirement
- unclear commercial quota
- unclear hands-on expectation
- unclear reporting line

An evidence gap should reduce confidence. It should not be silently converted into either a positive or negative fact.

### `evidence_anchors`

Specific evidence supporting assessment conclusions.

Anchors should remain traceable to their assessment/job.

They are evidence snippets or evidence statements, not a replacement for the original job description.

Because the aggregate field can be large, each anchor is indexed as a separate semantic unit.

---

## 5. Role-family fields

### `primary_role_family`

Primary classification of the role.

Used for structured grouping/analytics.

### `secondary_role_family`

Secondary classification where a role spans more than one family.

Role-family labels are explicit classifications and should not automatically replace semantic similarity search.

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

The golden questions use thresholds such as `>= 8`, but the precise allowed scale and null semantics should be verified against the physical schema/assessment contract before adding validation logic.

---

## 7. Decision fields

The evaluation contract currently references both:

```text
user_decision
decision
```

and values such as:

```text
DO_NOT_PURSUE
GO
NO_GO
```

This is a known naming inconsistency in the current contract.

Before implementation:

1. inspect the physical schema
2. identify the canonical decision column and vocabulary
3. normalise the documentation/tests rather than supporting ambiguous aliases indefinitely

Do not guess that `decision` and `user_decision` are different concepts without schema evidence.

---

## 8. `material_mandate_dimensions`

Represents dimensions of the mandate used for qualitative analysis of areas of strength/weakness.

The exact physical representation and controlled vocabulary should be verified before implementation.

If stored as structured JSON/list data, prefer deterministic parsing before LLM synthesis.

Do not assume it has the same indexing behaviour as the documented semantic list fields unless explicitly added to the indexing contract.

---

## 9. Source evidence vs assessment interpretation

Keep this distinction explicit.

### Source evidence

Primarily:

```text
job_description
```

and external/source-derived factual job metadata.

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
evidence_anchors
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

Actual model used after configuration/routing resolution.

### `total_tokens`

Total token usage recorded for the call.

### `pipeline_step`

Logical step within a larger workflow.

### `duration_seconds`

Observed duration of the call/step.

### `retry_number`

Retry attempt number.

### `status`

Success/failure status.

### `failure_category`

Normalised category for failure analysis.

Prefer categories over relying only on free-text exception messages.

### `version_metadata`

Version information associated with the call.

The evaluation contract also references `prompt_version`; confirm whether this is a dedicated field or represented inside version metadata.

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

## 12. Semantic indexing summary

Current indexing policy:

### One vector per populated scalar

```text
role_snapshot
real_mandate
technical_bar
decision_reason
```

### One vector per meaningful list item

```text
strong_fit_signals
red_flags
sustainability_risks
evidence_gaps
evidence_anchors
```

### Chunked

```text
job_description
```

See `docs/indexing.md` for the technical indexing contract.
