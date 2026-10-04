"""Regression checks for Python discovery in the shared PowerShell entry point."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PythonDiscoveryTest(unittest.TestCase):
    def test_multiple_python_matches_select_first_executable(self) -> None:
        shell = shutil.which("pwsh") or shutil.which("powershell")
        self.assertIsNotNone(shell, "Development checks require PowerShell")
        script = Path(__file__).resolve().parents[1] / "dev.ps1"
        # Load only the resolver, avoiding setup's environment mutations and exit.
        harness = r"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors)
$resolver = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Resolve-Python'
}, $true)
Invoke-Expression $resolver.Extent.Text
$venvPython = 'unused'
function Test-Path { return $false }
function Get-Command {
    param($Name, $CommandType, $ErrorAction)
    [pscustomobject]@{ Source = '/first path/python' }
    [pscustomobject]@{ Source = '/second/python' }
}
foreach ($explicit in @('', 'python')) {
    $Python = $explicit
    $resolved = Resolve-Python
    if ($resolved.Executable -isnot [string] -or $resolved.Executable -ne '/first path/python') {
        throw "Expected first executable for explicit='$explicit'; got $($resolved.Executable)"
    }
    if ($resolved.Prefix.Count -ne 0) { throw 'Unexpected launcher prefix' }
}
"""
        with tempfile.TemporaryDirectory() as directory:
            harness_path = Path(directory) / "discovery.ps1"
            harness_path.write_text(harness, encoding="utf-8")
            result = subprocess.run(
                [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(harness_path), str(script)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
