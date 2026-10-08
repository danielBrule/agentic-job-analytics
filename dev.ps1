#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("help", "setup", "check", "test")]
    [string]$Task = "help",
    [string]$Python,
    [string]$BaseRef
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$venvPython = if ($env:OS -eq "Windows_NT") {
    Join-Path $repoRoot ".venv/Scripts/python.exe"
} else {
    Join-Path $repoRoot ".venv/bin/python"
}

function Invoke-Tool {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE."
    }
}

function Resolve-Python {
    if ($Python) {
        $command = Get-Command $Python -CommandType Application -ErrorAction Stop | Select-Object -First 1
        return [pscustomobject]@{ Executable = $command.Source; Prefix = @() }
    }
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        return [pscustomobject]@{ Executable = $venvPython; Prefix = @() }
    }
    foreach ($name in @("python", "python3", "py")) {
        # Multiple PATH matches must not become one concatenated executable path.
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            $prefix = if ($name -eq "py") { @("-3") } else { @() }
            return [pscustomobject]@{ Executable = $command.Source; Prefix = @($prefix) }
        }
    }
    throw "Python 3.12+ was not found. Install it or pass -Python with its executable path."
}

function Invoke-Python {
    param([string[]]$Arguments)
    Invoke-Tool -Executable $pythonCommand.Executable -Arguments (@($pythonCommand.Prefix) + $Arguments)
}

Push-Location -LiteralPath $repoRoot
try {
    if ($Task -eq "help") {
        Write-Host @"
Usage: ./dev.ps1 <target> [-Python <executable>] [-BaseRef <commit>]

setup  Create .venv and install the pinned development dependency.
check  Validate public YAML/JSON, Markdown links, references, tests and whitespace.
test   Run all tests under tests/, including dev.ps1 regression tests.
help   Show this help.

BaseRef optionally checks committed changes as well as local/staged whitespace.
"@
        exit 0
    }

    $pythonCommand = Resolve-Python
    Invoke-Python -Arguments @("-c", "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ is required for development checks'")

    if ($Task -eq "setup") {
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            Invoke-Python -Arguments @("-m", "venv", (Join-Path $repoRoot ".venv"))
        }
        Invoke-Tool -Executable $venvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-dev.txt")
        Write-Host "Development environment ready. Run ./dev.ps1 check."
        exit 0
    }

    if ($Task -eq "check") {
        Invoke-Python -Arguments @("tools/check_repository.py")
    }
    Invoke-Python -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v")

    if ($Task -eq "check") {
        Invoke-Tool -Executable "git" -Arguments @("diff", "--check")
        Invoke-Tool -Executable "git" -Arguments @("diff", "--cached", "--check")
        if ($BaseRef -and $BaseRef -notmatch "^0+$") {
            Invoke-Tool -Executable "git" -Arguments @("diff", "--check", $BaseRef, "HEAD", "--")
        } elseif ($BaseRef) {
            # A newly created branch has an all-zero GitHub "before" SHA.
            Invoke-Tool -Executable "git" -Arguments @("show", "--format=", "--check", "HEAD", "--")
        }
        Write-Host "All development checks passed."
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    Pop-Location
}
