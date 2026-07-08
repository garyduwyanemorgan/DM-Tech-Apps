<#
.SYNOPSIS
  One-command release automation (Windows wrapper around scripts/release.sh).
.DESCRIPTION
  Bumps VERSION + frontend/package.json, rolls CHANGELOG.md from commits since the
  last tag, commits, annotated-tags vX.Y.Z, and pushes with the tag.
.EXAMPLE
  .\scripts\release.ps1 minor
  .\scripts\release.ps1 -v 1.0.0
  .\scripts\release.ps1 patch -DryRun
#>
param(
  [ValidateSet('patch','minor','major','auto')] [string]$Bump = 'patch',
  [string]$Version,
  [switch]$DryRun,
  [switch]$NoPush
)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sh = Join-Path $scriptDir 'release.sh'

# Locate a bash (git-bash) — PATH first, then common Git for Windows locations.
$bash = (Get-Command bash -ErrorAction SilentlyContinue).Source
if (-not $bash) {
  foreach ($p in @(
      "$env:ProgramFiles\Git\bin\bash.exe",
      "$env:ProgramFiles\Git\usr\bin\bash.exe",
      "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
      "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe")) {
    if (Test-Path $p) { $bash = $p; break }
  }
}
if (-not $bash) { throw "bash (Git for Windows) not found. Install Git, or run scripts/release.sh directly." }

$args = @()
if ($Version) { $args += @('-v', $Version) } else { $args += $Bump }
if ($DryRun)  { $args += '--dry-run' }
if ($NoPush)  { $args += '--no-push' }

& $bash $sh @args
exit $LASTEXITCODE
