"""Regression checks for the public repository validator."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
import yaml

from tools.check_repository import CheckFailure, check_contracts, check_documents, public_files


class RepositoryChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def contracts(self) -> None:
        self.write("evals/golden_questions.yaml", "version: 1\nreadiness_baseline:\n  date: '2026-10-06'\n  data_scope: initial_fixture_pack\nquestions:\n  - id: q01\n    readiness:\n      definition: specified\n      data_coverage: available\n      reference: exact-facts\n")
        self.write("evals/indexing_cases.yaml", "version: 1\ncases:\n  - id: first_case\n")
        self.write("evals/fixtures/reference_queries.json",
                   '{"golden_questions_version": 1, "references": [{"id": "q01", "status": "exact_sql_reference", "sql": "SELECT 1"}]}')

    def test_ignored_private_data_is_not_read(self) -> None:
        self.write(".gitignore", "data/\n.env\n")
        self.write("README.md", "# Public\n")
        self.write("data/private.json", "{invalid private data")
        self.write(".env", "PRIVATE_VALUE=do-not-read\n")
        paths = {path.relative_to(self.root).as_posix() for path in public_files(self.root)}
        self.assertEqual(paths, {".gitignore", "README.md"})

    def test_tracked_private_data_fails_before_parsing(self) -> None:
        self.write("data/private.json", "{invalid private data")
        subprocess.run(["git", "-C", str(self.root), "add", "data/private.json"], check=True)
        with self.assertRaisesRegex(CheckFailure, "private"):
            public_files(self.root)

    def test_private_boundary_artifacts_fail_before_parsing(self) -> None:
        for name in ("logs/run.json", "traces/run.json", "exports/dataset.json",
                     "checkpoints/thread.json", "outside.db-journal", "outside.sqlite-wal",
                     "outside.sqlite3-shm", "outside.log"):
            with self.subTest(name=name):
                path = self.write(name, "{invalid private content")
                with self.assertRaisesRegex(CheckFailure, "private"):
                    public_files(self.root)
                path.unlink()

    def test_repository_ignore_rules_cover_private_artifacts(self) -> None:
        self.write(".gitignore", (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8"))
        for name in ("logs/run.json", "traces/run.json", "exports/dataset.json",
                     "checkpoints/thread.json", "outside.db", "outside.sqlite", "outside.sqlite3",
                     "outside.db-wal", "outside.db-shm", "outside.db-journal",
                     "outside.sqlite-wal", "outside.sqlite3-shm", "outside.log"):
            with self.subTest(name=name):
                self.write(name, "private synthetic artifact")
                result = subprocess.run(["git", "-C", str(self.root), "check-ignore", "--quiet", name])
                self.assertEqual(result.returncode, 0)
        self.write("evals/public.json", "{}")
        self.assertIn(self.root / "evals/public.json", public_files(self.root))

    def test_new_untracked_documents_are_checked(self) -> None:
        self.write("README.md", "[missing](absent.md)\n")
        with self.assertRaisesRegex(CheckFailure, "absent.md"):
            check_documents(self.root, public_files(self.root))

    def test_relative_links_and_duplicate_heading_anchors(self) -> None:
        readme = self.write("README.md", "[second](docs/guide.md#setup-1)\n")
        guide = self.write("docs/guide.md", "# Setup\n\n# Setup\n")
        check_documents(self.root, [readme, guide])

    def test_missing_anchor_fails(self) -> None:
        readme = self.write("README.md", "[missing](guide.md#missing)\n")
        guide = self.write("guide.md", "# Present\n")
        with self.assertRaisesRegex(CheckFailure, "missing"):
            check_documents(self.root, [readme, guide])

    def test_code_samples_are_not_treated_as_links_or_headings(self) -> None:
        path = self.write("README.md", "# Real\n\n```text\n# Fake\n[example](absent.md)\n```\n[real](#real)\n")
        check_documents(self.root, [path])

    def test_unclosed_code_fence_fails(self) -> None:
        path = self.write("README.md", "```python\nprint('example')\n")
        with self.assertRaisesRegex(CheckFailure, "fence"):
            check_documents(self.root, [path])

    def test_link_outside_repository_fails(self) -> None:
        path = self.write("README.md", "[outside](../outside.md)\n")
        with self.assertRaisesRegex(CheckFailure, "outside"):
            check_documents(self.root, [path])

    def test_document_errors_with_equivalent_root_spelling(self) -> None:
        # An unresolved alias reproduces the short/long path mismatch from Windows CI.
        (self.root / "alias").mkdir()
        root = self.root / "alias" / ".."
        guide = self.write("guide.md", "# Present\n")
        for content, message in (
            ("[missing](absent.md)\n", "missing or ignored link"),
            ("[outside](../outside.md)\n", "link outside repository"),
            ("[anchor](guide.md#missing)\n", "missing anchor"),
            ("```python\n", "Unclosed Markdown code fence"),
        ):
            with self.subTest(message=message):
                readme = self.write("README.md", content)
                with self.assertRaisesRegex(CheckFailure, f"README.md: {message}"):
                    check_documents(root, [readme, guide])

    def test_valid_contracts(self) -> None:
        self.contracts()
        check_contracts(self.root)

    def test_question_readiness_is_complete_and_uses_known_tags(self) -> None:
        self.contracts()
        path = self.root / "evals/golden_questions.yaml"
        original = yaml.safe_load(path.read_text(encoding="utf-8"))
        for field in ("definition", "data_coverage", "reference"):
            for invalid in (None, "passed", ["available"]):
                with self.subTest(field=field, invalid=invalid):
                    data = yaml.safe_load(yaml.safe_dump(original))
                    if invalid is None:
                        del data["questions"][0]["readiness"][field]
                    else:
                        data["questions"][0]["readiness"][field] = invalid
                    path.write_text(yaml.safe_dump(data), encoding="utf-8")
                    with self.assertRaisesRegex(CheckFailure, "q01.*readiness"):
                        check_contracts(self.root)

    def test_readiness_baseline_requires_date_and_scope(self) -> None:
        self.contracts()
        path = self.root / "evals/golden_questions.yaml"
        original = yaml.safe_load(path.read_text(encoding="utf-8"))
        for baseline in (None, {}, {"date": "yesterday", "data_scope": "fixtures"},
                         {"date": "2026-02-30", "data_scope": "fixtures"},
                         {"date": "2026-10-06", "data_scope": ""}):
            with self.subTest(baseline=baseline):
                data = dict(original, readiness_baseline=baseline)
                path.write_text(yaml.safe_dump(data), encoding="utf-8")
                with self.assertRaisesRegex(CheckFailure, "readiness baseline"):
                    check_contracts(self.root)

    def test_duplicate_yaml_keys_fail(self) -> None:
        self.contracts()
        self.write("evals/golden_questions.yaml", "version: 1\nversion: 2\nquestions: []\n")
        with self.assertRaisesRegex(CheckFailure, "Duplicate"):
            check_contracts(self.root)

    def test_duplicate_case_ids_fail(self) -> None:
        self.contracts()
        self.write("evals/indexing_cases.yaml", "version: 1\ncases:\n  - id: same\n  - id: same\n")
        with self.assertRaisesRegex(CheckFailure, "Duplicate"):
            check_contracts(self.root)

    def test_reference_version_mismatch_fails(self) -> None:
        self.contracts()
        self.write("evals/fixtures/reference_queries.json",
                   '{"golden_questions_version": 2, "references": []}')
        with self.assertRaisesRegex(CheckFailure, "version"):
            check_contracts(self.root)

    def test_reference_to_unknown_question_fails(self) -> None:
        self.contracts()
        self.write("evals/fixtures/reference_queries.json",
                   '{"golden_questions_version": 1, "references": [{"id": "q99", "status": "exact_sql_reference", "sql": "SELECT 1"}]}')
        with self.assertRaisesRegex(CheckFailure, "q99"):
            check_contracts(self.root)

    def test_cli_failure_returns_nonzero(self) -> None:
        self.write("README.md", "[broken](absent.md)\n")
        checker = Path(__file__).resolve().parents[1] / "tools/check_repository.py"
        result = subprocess.run([sys.executable, str(checker), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("absent.md", result.stderr)

    def test_cli_success_needs_no_private_database(self) -> None:
        self.contracts()
        checker = Path(__file__).resolve().parents[1] / "tools/check_repository.py"
        result = subprocess.run([sys.executable, str(checker), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicate_json_keys_fail(self) -> None:
        self.contracts()
        self.write("evals/fixtures/reference_queries.json",
                   '{"golden_questions_version": 1, "golden_questions_version": 2}')
        with self.assertRaisesRegex(CheckFailure, "Duplicate"):
            check_contracts(self.root)


if __name__ == "__main__":
    unittest.main()
