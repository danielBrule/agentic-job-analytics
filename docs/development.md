# Development workflow

The repository currently validates specifications, public evaluation definitions and q18/q19/q21 reference SQL using synthetic SQLite records. Runtime code, executable agent/indexing evaluations and deployment will be added later.

## Prerequisites and setup

Use Git, Python 3.12 or newer, and PowerShell. Windows PowerShell 5.1 is supported; use PowerShell 7 on Linux/macOS. CI uses Python 3.12 and PowerShell 7. These are development-tooling choices, not a selection of runtime model providers or infrastructure.

From the repository:

```powershell
./dev.ps1 setup
./dev.ps1 check
```

`setup` creates the ignored `.venv` and installs the pinned PyYAML development dependency from [requirements-dev.txt](../requirements-dev.txt). Python's standard library does not provide a YAML parser. The other checks and regression tests use the standard library.

If Python is not on PATH, pass its executable explicitly:

```powershell
./dev.ps1 setup -Python "C:/path/to/python.exe"
```

Subsequent commands prefer the repository's `.venv`. `-Python` also lets you select an existing development environment explicitly. Script paths are resolved from the repository, so the commands can be invoked from another working directory.

## Commands

| Command | Behaviour |
|---|---|
| `./dev.ps1 help` | List supported targets; this is the default |
| `./dev.ps1 setup` | Create/reuse `.venv` and install development dependencies |
| `./dev.ps1 check` | Validate public YAML/JSON, local Markdown links/anchors, acceptance/reference consistency, regression tests and Git whitespace |
| `./dev.ps1 test` | Run repository-validator and SQL-reference regression tests |
| `./dev.ps1 check -BaseRef origin/dev` | Also check whitespace in committed changes between that reference and HEAD |

Failures stop the target and produce a nonzero exit code. Local checks include tracked files and new, non-ignored files. They exclude private snapshots and environments through Git's ignore rules; accidentally tracked private paths fail before their contents are read. Checks validate inline Markdown links and heading anchors, not external website availability.

The tests exercise the development validator and [q18/q19 selection and q21 accounting](../tests/test_reference_queries.py) against synthetic in-memory SQLite data. Passing them does not mean the runtime agent or indexing acceptance cases have been implemented. See [evaluation fixtures](../evals/fixtures/README.md) for real-data references and review requirements.

Golden questions carry planning-only `readiness` tags for definition, data coverage and references, with a dated `readiness_baseline` identifying the fixture scope. Checks require complete tags with known values and a valid baseline date/scope; these tags do not skip acceptance requirements or establish passing results. Update them when reviewing readiness, and record dataset-specific readiness separately in versioned evaluation artifacts. The [initial audit](repository_audit.md) records foundation evidence and follow-up issues.

## Branches and CI

Use feature branches → pull request into `dev` → pull request into `main`. `dev` integrates ongoing work; `main` receives reviewed changes.

[ci.yml](../.github/workflows/ci.yml) runs on pushes to `dev`/`main`, pull requests targeting either branch, and manual dispatch. Windows and Linux jobs each call `dev.ps1 setup` followed by `dev.ps1 check`. CI supplies the pull-request base or previous push commit to check whitespace across the change range, as well as local/staged changes. A new branch's all-zero previous SHA falls back to checking its latest commit.

The workflow uses read-only repository permissions and pinned official actions. It accesses only public repository files and synthetic test inputs, with no model calls, source database, LangSmith upload or private-data artifacts.

Branch creation and merge enforcement are repository settings, not effects of adding a workflow file. After publishing the workflow and obtaining the first successful run:

1. Create/publish `dev` if it does not exist.
2. Configure rules for both `dev` and `main` requiring pull requests and the `check (ubuntu-latest)` and `check (windows-latest)` status checks.
3. Promote changes through pull requests; CI does not automatically merge or deploy.

Use [GitHub's protected-branch settings](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule) to enforce the checks. They are not enforced until those settings are enabled.

Add application linting, tests and build commands to `dev.ps1` as implementation arrives, keeping CI on the same entry point. Deployment requires a separately agreed application and hosting target.
