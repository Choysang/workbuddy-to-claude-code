param(
    [string]$AppDir,
    [string]$Output,
    [switch]$NoShortcuts,
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
$harnessArguments = @((Join-Path $PSScriptRoot 'scripts/harness.py'), 'build')
if ($AppDir) { $harnessArguments += @('--app-dir', $AppDir) }
if ($Output) { $harnessArguments += @('--output', $Output) }
if ($NoShortcuts) { $harnessArguments += '--no-shortcuts' }
if ($Launch) { $harnessArguments += '--launch' }
& python @harnessArguments
exit $LASTEXITCODE
