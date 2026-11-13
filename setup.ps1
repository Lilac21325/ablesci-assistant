param([switch]$InstallSkill, [string]$Python)
$ErrorActionPreference = 'Stop'
$venv = Join-Path $PSScriptRoot '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($Python) {
        & $Python -m venv $venv
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        & python.exe -m venv $venv
    } else {
        & py -3 -m venv $venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install project dependencies.' }

if ($InstallSkill) {
    $codexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $skillDir = Join-Path $codexDir 'skills\ablesci-paper-download'
    $skillFile = Join-Path $skillDir 'SKILL.md'
    $pathFile = Join-Path $skillDir 'assistant-path.txt'
    if ((Test-Path -LiteralPath $skillFile) -and -not (Test-Path -LiteralPath $pathFile)) {
        throw "A separate installation already exists at $skillDir. Move it before installing this copy."
    }
    New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'skill\ablesci-paper-download\SKILL.md') -Destination $skillFile
    [IO.File]::WriteAllText($pathFile, $PSScriptRoot)
    Write-Host "Installed Codex skill at $skillDir"
}
