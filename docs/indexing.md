# Indexing Architecture

## Purpose

This document defines how canonical SQLite job-search data becomes a semantic vector index.

The vector index is a derived, rebuildable search structure.

It is not a second source of truth.

Acceptance definitions live in [indexing_cases.yaml](../evals/indexing_cases.yaml). The executable indexing harness remains implementation work. Cases use sparse normalized indexing inputs to isolate behaviour; they are not complete physical source rows.

---

## 1. Architecture

```text
Copilot SQLite
  -> capture required tables in a candidate SQLite snapshot
  -> build/normalize units and compare with the published manifest
  -> reuse unchanged embeddings; embed only new/changed units
  -> retire obsolete units; remove deleted-job vector records
  -> validate candidate SQL/vector generation
  -> publish the matching pair together
```

---

## Snapshot ingestion and publication

Copilot SQLite remains canonical. The runtime serves a read-only analytics snapshot and the vector generation built for it. Consistency within that pair is required; immediate freshness against Copilot is not. Record and expose the source capture time and shared `generation_id` in application results and traces without private payloads.

1. Capture a consistent source copy using SQLite's native backup mechanism, then retain only the required analytics tables: `jobs`, `assessments` and `llm_calls`, plus supporting tables required by preserved foreign keys. Preserve source identifiers and schema semantics. The copy is disposable and rebuildable; do not modify upstream data. A raw main-file copy is not the ingestion contract.
2. Prepare a new candidate generation from this fixed snapshot. Compare source projections, semantic-unit membership, hashes and configuration with the published manifest. Reuse unchanged embeddings; embed only new or changed content unless embedding/index configuration requires wider work. SQL rows may all be copied at this small volume.
3. Keep candidate SQL and vector membership isolated from the published pair. Do not alter vector content, positions, filters or membership used by existing requests. Reusing immutable embeddings is allowed; creating a generation does not require new embeddings for unchanged units.
4. Validate the candidate: snapshot integrity and foreign keys, expected unit membership/content, source IDs and usable assessments, embedding/index versions, and equal SQL/vector `generation_id`. Reject a mismatched pair with `generation_mismatch`.
5. Publish one manifest/reference selecting both artifacts as one logical switch. New requests pin that pair for their entire execution. A request already using the previous generation finishes against that generation. Snapshot, embedding, upsert, validation or publication failure leaves the previous pair available and reports an explicit failure.
6. Retire old pairs after requests release them. Cleanup must not remove shared embeddings still referenced by a published or in-flight generation. Retaining superseded content is optional; retention and cleanup timing remain implementation choices. Removing a job from the next generation does not promise immediate erasure from old snapshots, traces or evaluation packs.

No pair is available before the first successful ingestion; report that state rather than mixing candidate or live data. Provider-specific generation storage and the publication mechanism will be selected during implementation. No real-time CDC or concurrent source-write assumption is needed for the initial local project, but use the backup mechanism for a consistent capture.

## Current source selection

Extract each job with zero or one current successful assessment, as mapped in [data_semantics.md](data_semantics.md). The checked Copilot source updates the same assessment row on successful reassessment and preserves it on failure. Only `ASSESSED` rows supply assessment-derived units; job descriptions remain indexable without an assessment.

Compare all currently expected units for the affected job/field with the manifest. Reassessment may leave the same `assessment_id` while changing content. Reuse unchanged units; deactivate units that no longer belong to the current successful result. Never make multiple assessment results active for one job.

A field change for job A does not re-embed job B or unrelated fields. Changes to embedding configuration or indexing rules may intentionally affect a broader set.

## 2. Indexed fields

### Scalar semantic field

The complete populated `technical_bar` field produces one unit, even when it contains several sentences or bullet-like formatting.

### Bullet-formatted assessment text

These fields remain scalar text in SQLite but produce one unit per meaningful bullet:

```text
role_snapshot
real_mandate
decision_reason
```

Recognise `-` or `*` after optional indentation at the start of a line, followed by whitespace. Preserve line boundaries until parsing is complete. Remove the marker, then normalize each bullet's content. Do not split on internal hyphens or asterisks.

Continuation lines belong to the preceding bullet. Treat whitespace-only marker content as empty. Preserve a nonempty preamble before the first bullet as one scalar unit. If there are no recognised markers, preserve the complete field as one scalar unit. Ignore empty units and deduplicate identical normalized bullets within the same job, assessment and field.

Do not use an LLM for bullet parsing or split these short fields by arbitrary character limits. Retrieve parent context when a bullet is insufficient on its own.

### List semantic fields

Each meaningful parsed list item produces one semantic unit:

```text
strong_fit_signals
red_flags
sustainability_risks
evidence_gaps
evidence_anchors
```

Do not embed the serialized list as one vector.

Example source:

```text
["Heavy travel", "Large business-development target"]
```

becomes two semantic units.

### Evidence-anchor objects

The checked source stores `evidence_anchors` as JSON objects with `source_reference`, `evidence` and `supports`, not as strings. Each anchor still produces one unit. Render its semantic text deterministically:

```text
Evidence: <evidence>
Supports: <supports>
```

Keep `source_reference` as metadata and preserve the complete canonical object in SQLite. `evidence` is candidate-profile evidence from Document A; `supports` is its assessment interpretation. Do not relabel either as a job-description quote or embed serialized JSON. Empty/malformed required values are explicit parsing errors.

For anchor identity, include `source_reference` as well as rendered content when distinct references would otherwise collide. Exact duplicate anchors within the same job/assessment/field may be deduplicated. Metadata-only changes can reuse embeddings when rendered content is unchanged.

### Long-form field

```text
job_description
```

A job description is chunked when it is too large to be a useful single retrieval unit.

---

## 3. Why fine-grained semantic units

The indexing model optimises retrieval precision rather than minimising vector count.

Example query:

> roles with concerns around stakeholder management

A dedicated `red_flags` item such as:

```text
"Significant daily C-suite stakeholder exposure"
```

is a cleaner semantic match than a vector representing several unrelated assessment fields.

The trade-off is more vectors and therefore a need for job-level grouping during retrieval.

That trade-off is intentional.

---

## 4. Semantic-unit model

Each indexed unit should expose at least:

```text
semantic_unit_id
job_id
field_name
unit_type
content
content_hash
source_version
source_updated_at
is_active
indexed_at
embedding_model
embedding_version
index_schema_version
```

Assessment-derived units should also retain:

```text
assessment_id
```

Where useful:

```text
unit_position
source_reference
```

Allowed logical `unit_type` values:

```text
scalar
bullet
list_item
chunk
```

### Provenance naming

Keep one logical metadata vocabulary: `field_name` identifies the source field, `unit_type` identifies its representation, and `semantic_unit_id` identifies the unit. Description chunks also carry `unit_position`. These fulfil document-type and chunk-ID provenance needs without parallel aliases.

`source_updated_at` maps to `jobs.updated_at` or `assessments.updated_at`, according to the owning record. The source has no native `source_version` counter; compute an opaque deterministic source-revision token. Whole-second timestamps are not unique versions, so semantic content hashes must catch changes even when timestamps match. `indexed_at` records when a unit's indexed state was last synchronized and must not be used as evidence of source freshness.

`index_schema_version` is the document/semantic-unit schema version. `embedding_model` identifies the model and `embedding_version` tracks model/configuration revisions. If a provider exposes a model revision, include it in that configuration's recorded provenance. The verified mappings and physical-deletion semantics are documented in `docs/data_semantics.md`. Generation identity belongs to the pair manifest/membership and is separate from these per-unit versions.

---

## 5. Identity

Semantic-unit identity should be deterministic where practical.

### Scalar

Conceptually:

```text
job_id + assessment_id + field_name
```

### List item

Conceptually:

```text
job_id + assessment_id + field_name + normalized_content_hash
```

The list position must not be the sole identity.

Reordering:

```text
[A, B, C]
```

to:

```text
[B, A, C]
```

must not force re-embedding of unchanged items.

### Assessment bullet

Conceptually:

```text
job_id + assessment_id + field_name + normalized_content_hash
```

Bullet position and marker style are not identity. Reordering bullets or replacing `-` with `*` must not force re-embedding. A changed bullet deactivates its previous record and creates a new active one. Nonempty preamble or unmarked fallback text uses scalar identity.

### Active and obsolete records

`is_active` identifies current units within the selected generation. Superseded bullets, items and scalar revisions must not be searchable. They may be deactivated and retained or physically removed from the candidate generation; historical reconstruction is not required.

Exactly one current record belongs to each logical unit/configuration in the candidate generation. Scalar identity stays stable; storage IDs can distinguish content/configuration revisions. Generation membership must isolate any shared vector records from changes while older requests use them. Failed replacement embedding/upsert must not publish partial membership. See [snapshot ingestion and publication](#snapshot-ingestion-and-publication).

### Job-description chunk

Chunk identity must distinguish chunks belonging to the same job and support change detection.

Exact chunk identity is implementation-specific because chunk boundaries may change when source text changes.

Do not expose storage-engine-specific IDs as domain identifiers.

---

## 6. Normalisation

Parsing occurs before content normalisation. Preserve line boundaries while identifying bullets; normalise extracted unit content before hashing and embedding.

At minimum:

- trim leading/trailing whitespace
- normalise repeated whitespace
- ignore null values
- ignore empty/whitespace-only values
- parse serialized list fields
- index list items separately
- parse bullet-formatted fields at line-start markers and retain continuation lines
- normalise marker style out of bullet content

Normalisation should be deterministic.

A whitespace-only source change should not cause a new embedding.

Do not over-normalise semantically meaningful punctuation or wording without evidence that retrieval improves.

---

## 7. Duplicate list items and bullets

Within the same:

```text
job_id
assessment_id
field_name
```

identical normalised string-list items or bullets should not produce duplicate active semantic units. Object anchors preserve distinct source references as defined above.

Identical text across different jobs remains separate because each unit belongs to a different parent entity.

---

## 8. Job-description chunking

Job descriptions are materially longer than the assessment scalar fields and should support multiple chunks.

Prefer natural boundaries where practical:

- headings
- paragraphs
- bullet groups
- sections

Avoid blindly splitting in the middle of a meaningful unit when a nearby natural boundary exists.

The exact chunk size and overlap are implementation configuration, not a domain contract.

Tune them through retrieval evaluation rather than hard-coding them into the semantic model.

Each chunk must preserve:

```text
job_id
field_name = job_description
unit_type = chunk
unit_position
content_hash
source_version
source_updated_at
is_active
indexed_at
```

---

## 9. Incremental indexing

Indexing is incremental.

For each candidate unit:

1. normalise content
2. compute `content_hash`
3. compare with the current indexed state
4. embed only if required

### New unit

```text
embed
insert
```

### Unchanged unit

```text
reuse existing embedding
update non-semantic metadata if required
```

### Changed scalar

```text
embed replacement for changed technical_bar or unmarked fallback/preamble only
activate replacement and deactivate previous record
```

### Added, removed, changed or reordered bullet

Apply the same content-based incremental rules as list items below. Embed only new or changed bullets, deactivate removed bullets, and update positions without embedding on reorder.

### Added list item

```text
embed new item only
```

### Removed list item

```text
deactivate old item
do not re-embed remaining items
```

### Reordered list

```text
update position metadata if needed
do not re-embed
```

---

## 10. Idempotency

Running the indexer repeatedly against unchanged source data must produce:

- no duplicate active units
- no unnecessary embedding calls
- no semantic changes to the index

Idempotency is a required behaviour, not an optimisation.

---

## 11. Versioning

Track three distinct version concepts.

### `source_version`

Opaque derived revision token identifying the source state used for this unit. The checked upstream has no native version counter; the token must not be mistaken for a source column.

Used to identify whether source state changed.

A source-version change does not automatically require re-embedding if the semantic content hash is unchanged.

### `embedding_version`

Version of embedding configuration.

May encode changes such as:

- embedding model
- dimensionality
- preprocessing that affects embeddings

Changing this version can require re-embedding otherwise unchanged units.

### `index_schema_version`

Version of the semantic-unit/index contract.

Use for controlled migrations when unit structure or indexing semantics change.

Do not overload one version field to represent all three concepts.

An existing index built with one unit per assessment scalar is incompatible with bullet-level units. When migrating such an index, increment `index_schema_version` and rebuild or migrate affected fields. Deactivate old whole-field units when replacing them with bullets; do not leave both representations active. For a new index, initialise the schema version for the implemented contract. The version in `evals/indexing_cases.yaml` tracks acceptance definitions separately from the runtime index schema version.

---

## 12. Deletion

Physical deletion from Copilot is detected by comparing a complete successful candidate snapshot with the published generation. Remove all active and obsolete vector records for a missing job from the candidate generation. Classify the missing record as `source_record_missing`; do not invent soft-deletion fields or timestamps. Failed or partial reads must not infer deletion or publish a new pair.

Default semantic retrieval selects the pinned generation's membership and `is_active = true`. A job missing from that generation's SQLite snapshot cannot appear in its semantic results. Jobs closed or rejected but still present remain available for analytics.

The previous published pair may still contain an upstream-deleted job until successful publication, and in-flight requests can finish on that pair. Cleanup follows the generation lifecycle above. If a job is reintroduced later, derive units from its current snapshot content; reuse embeddings only if their content/configuration match. Soft deletion and restoration flags are outside initial scope.

---

## 13. Index metadata vs canonical data

The vector store may duplicate limited metadata needed for:

- filtering
- reconstruction
- version checks
- deletion checks

Examples:

```text
job_id
assessment_id
field_name
unit_type
is_active
source_version
source_updated_at
```

Canonical business attributes still belong to SQLite.

For example, use SQLite as the authoritative value for:

- company
- title
- current application status
- scores
- dates

---

## 14. Retrieval implications

Fine-grained indexing means semantic results must be reconstructed to jobs.

Example:

```text
job_42 / red_flags / hit
job_42 / sustainability_risks / hit
job_17 / real_mandate / hit
```

represents two jobs, not three.

Indexing must preserve identifiers and provenance that support job-level grouping and canonical reconstruction. Runtime ranking, context expansion and synthesis are defined in [retrieval_contract.md](retrieval_contract.md#11-semantic-scope-and-job-level-ranking).

---

## 15. Field-aware search

Store `field_name` as filterable metadata so retrieval can select semantic dimensions without requiring a separate physical index for each field. Runtime field-selection hints and their limits are defined in [retrieval_contract.md](retrieval_contract.md#9-field-aware-semantic-retrieval).

---

## 16. Rebuildability

The vector index must be rebuildable entirely from:

```text
SQLite
+
indexing configuration
+
embedding configuration
```

No unique business information may exist only in the vector store.

A full rebuild should produce behaviourally equivalent semantic units for the same source/configuration.

---

## 17. Scaling

The semantic model should not change merely because vector count grows.

Capacity depends on embedding dimensions, metadata filters, backend, hardware and workload. Measure latency, memory, indexing throughput and cost rather than assuming a vector-count threshold guarantees a particular deployment size.

Before coarsening semantic units solely to reduce vector count, consider:

- metadata filtering
- ANN tuning
- job-level grouping
- reranking
- partitioning
- batch embedding/indexing

Evaluate granularity against all equally important [engineering criteria](../AGENTS.md#1-engineering-principles). Existing unit contracts remain requirements; a material conflict or proposed contract change goes to the human with evidence.

---

## 18. Evaluation boundary

[Indexing cases](../evals/indexing_cases.yaml) define transformation and index-lifecycle acceptance. [Golden questions](../evals/golden_questions.yaml) define user-facing retrieval acceptance; internal indexing changes alone do not change them. See [architecture.md](architecture.md#evaluation-and-observability) for metrics and [evaluation fixtures](../evals/fixtures/README.md) for real-data coverage and controlled synthetic transitions.
