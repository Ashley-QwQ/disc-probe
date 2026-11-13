param(
    [string]$Lab,
    [string]$Python = "python",
    [string]$Config = (Join-Path $PSScriptRoot "dvd-r-3.json")
)
$ErrorActionPreference = "Stop"
$savedEncoding = [Console]::OutputEncoding
$savedPythonEncoding = $env:PYTHONIOENCODING
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = "utf-8"
$configPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Config)
$runArgs = @("-B", "-m", "disclab.examples", "--config", $configPath)
if ($Lab) {
    $labPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Lab)
    $runArgs += @("--lab", $labPath)
}
if (Test-Path -LiteralPath $Python -PathType Leaf) {
    $Python = (Get-Item -LiteralPath $Python).FullName
}
Push-Location (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent)
try {
    & $Python @runArgs
    if ($LASTEXITCODE -ne 0) { throw "Disc Lab example failed (exit $LASTEXITCODE)." }
} finally {
    Pop-Location
    [Console]::OutputEncoding = $savedEncoding
    $env:PYTHONIOENCODING = $savedPythonEncoding
}
