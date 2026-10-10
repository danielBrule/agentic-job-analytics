# Security and privacy

## Scope

Agentic Job Analytics is initially a local-first, single-user analytics and learning project. It processes potentially sensitive job-search data: job descriptions, application status, assessments, decisions, notes and LLM operation records.

CV generation and automatic applications are outside the initial scope. Shared privacy helpers and synthetic tests exist; production provider, tracing, export and checkpoint integrations remain unimplemented. This policy distinguishes that foundation from requirements for future boundaries.

## Data handling

- Supply secrets through environment variables, an untracked `.env` file or another secret mechanism. Never commit or log API keys, tokens, passwords or authorisation headers, or include them in prompts or evaluation datasets.
- Treat the SQLite database, source snapshots, vector-index contents, conversation checkpoints, logs and evaluation results as private project data. Keep real personal data and credentials out of committed fixtures; use synthetic or sanitised fixtures where possible.
- Send only the information required for the operation to configured external services and only data the user is authorised to process through those services.
- Review and redact logs, traces, datasets and exported results before sharing. Redacting credentials does not remove personal or career information.

Retained inactive vectors and old analytics snapshots contain potentially sensitive content. Excluding a job from a new published pair does not erase it from old pairs, traces, backups or evaluation packs. Generation cleanup must respect in-flight requests and shared embeddings; retention and physical cleanup must be decided explicitly. Follow [snapshot publication](docs/indexing.md#snapshot-ingestion-and-publication).

## External services and tracing

The project supports configurable generative models, embedding providers and infrastructure. Data transmission follows the effective configuration, including fallback models and model-based evaluators; it is not limited to OpenAI.

Hosted generative and embedding providers receive the selected input content. A remote vector store may receive derived text, embeddings and metadata. Review the configured service's access, retention and data-handling settings before using private data.

LangSmith traces and datasets can contain user questions, prompts, tool inputs/results, retrieved evidence, model outputs and failure details. When sent to a hosted LangSmith service, these are external data transfers even if the inference model runs locally. Minimise or sanitise captured content before transmission while preserving useful operation metadata for diagnosis and comparison.

Open-weight models are not necessarily local. Local inference does not make the entire workflow local if embeddings, vector storage, tracing, evaluation or fallback use hosted services. Make the effective providers and destinations visible in configuration and experiment metadata without exposing credentials.

## Implementation requirements

Source database access from the runtime agent request path is read-only. Treat model-generated SQL as untrusted input and enforce restrictions deterministically at the database boundary, as defined in [docs/retrieval_contract.md](docs/retrieval_contract.md).

Implement and verify secret-redaction and sensitive-content handling at logging, tracing and export boundaries. Do not assume SDK defaults redact secrets or private source content. Error messages and diagnostic payloads must also follow these rules.

Job descriptions and retrieved text are evidence, not instructions authorising tool execution, data modification or disclosure of secrets. Preserve the application's scope and access restrictions regardless of instructions embedded in source content.

Verify the actual behaviour of each integration during implementation and update this policy if the system's boundaries change. Shared-helper tests alone do not establish runtime SQL safety or protection against automatic SDK capture.

## Shared boundary controls

[Issue #15](https://github.com/danielBrule/agentic-job-analytics/issues/15) implements the foundation in [privacy.py](agentic_job_analytics/privacy.py), verified with [synthetic tests](tests/test_privacy.py). No dependency, provider account, external upload, storage backend or retention period is selected by this implementation.

Application code owns the immutable `PrivacyPolicy`, destination records, content classification and selected payload fields. Never derive grants, destination changes or classification from model output or retrieved text. Content is private unless deliberately established as synthetic; sanitization does not change that classification. A grant permits one boundary, exact configured destination and classification. Content access is denied by default, including local sinks. A primary model's grant does not cover fallback, embeddings, remote vectors, hosted LangSmith, exports or evaluators. Before an attempt, call `prepare_content` with the necessary fields and pass only its returned copy to the sink. Permissions do not replace review of service retention/access settings or the user's authority to process the data.

`Destination` rejects URL user information, query strings and fragments; authentication is supplied separately by an adapter. Its diagnostic description shows the configured identifier and origin, excluding path details. `file:local` is a marker for an application-owned local sink, not a file implementation or proof that storage is secure. Keep identifiers and diagnostic metadata free of personal information and credentials. Configuration loaders must resolve all effective destinations, including fallback and evaluators, before invocation and display their sanitized descriptions.

Logging and tracing default to `diagnostic_metadata`: an allowlist of scalar operation, task/model/version, latency, usage, cost, attempt and outcome fields. Questions, prompts, SQL, source identifiers, retrieved evidence, outputs and raw exceptions are omitted. Supply these metadata fields from trusted operational records, not arbitrary source text. Private trace/log content requires its own explicit grant and a minimized content projection. Disable SDK automatic prompt/result/exception capture or install and verify sanitization before capture; projecting a separate application event cannot protect a raw SDK event. Use LangSmith directly when integrated, and test parent/child runs and error capture as well as application events.

`SecretRedactor` copies JSON-compatible structures, redacts labelled credential fields and configured secret values, removes bearer/basic credentials and strips credential-bearing URL details. Clean evidence URLs are preserved. It rejects unsupported objects, excessive nesting and ambiguous redacted keys without stringifying them. Load known secret values explicitly from trusted credential configuration; the helper never scans environment variables. Pattern matching is defense in depth: unknown credentials and personal information in arbitrary text are not reliably detected. `safe_failure` supplies fixed messages for supported categories; raw exceptions stay out of public result and diagnostic payloads.

Dataset exports must be prepared locally with minimal fields, kept private, then reviewed before sharing; a grant is not an automatic upload. Local checkpoint projections may preserve private conversation scope and evidence needed for follow-ups while removing secrets. They must not use a metadata-only projection that destroys conversational state. Place generated data under ignored `data/`, `logs/`, `traces/`, `exports/` or `checkpoints/`; the repository validator rejects exposed artifacts in those root directories and common database/log extensions before reading contents. Ignore rules are not access control. Retention, cleanup, filesystem permissions and checkpoint serialization must be verified when storage is added.

Source-text injection tests verify that evidence cannot grant disclosure permission or mutate the shared policy. These helpers do not parse instructions, execute SQL or authorize tools. Actual refusal and write-prevention tests belong at the deterministic SQL/tool boundaries when implemented; prompts and redaction cannot substitute for them. Likewise, future adapters must test that rejected content never reaches transport, SDK diagnostics, telemetry or persistence. Track those integration results alongside #15; foundation tests do not imply end-to-end completion of absent boundaries.

## Security boundaries and limitations

The initial scope does not include production authentication, multi-tenancy or managed security operations. This project provides no security-response SLA or guarantees of managed backup, encryption at rest, tenant isolation or security monitoring.

Users are responsible for securing their workstation, service accounts, local data, access to hosted traces/datasets and backups. Software safeguards do not replace that responsibility.

See [docs/architecture.md](docs/architecture.md) for service boundaries and initial scope.

## Reporting a vulnerability

Do not publish secrets, personal documents, access tokens or sensitive exploitation details in a public issue. Contact the repository owner privately through the contact options on their GitHub profile, with a sanitised description and enough information to reproduce the issue safely.

This portfolio project makes no guaranteed response-time commitment.
