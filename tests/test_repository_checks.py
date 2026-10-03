"""Regression checks for the public repository validator."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

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
        self.write("evals/golden_questions.yaml", "version: 1\nquestions:\n  - id: q01\n")
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

    def test_valid_contracts(self) -> None:
        self.contracts()
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
