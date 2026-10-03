# Resolve only an existing installed Runner; never search unrelated project folders.
$ErrorActionPreference = 'Stop'
$registeredRoot = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner' -ErrorAction SilentlyContinue).InstallLocation
if ($registeredRoot) {
    $registeredRunner = Join-Path $registeredRoot 'runner.exe'
    if (Test-Path -LiteralPath $registeredRunner -PathType Leaf) { Write-Output $registeredRunner; exit 0 }
}
$defaultRunner = Join-Path $env:LOCALAPPDATA 'Programs\AgentRunner\runner.exe'
if (Test-Path -LiteralPath $defaultRunner -PathType Leaf) { Write-Output $defaultRunner; exit 0 }
throw 'AgentRunner is not installed. Install it before submitting a task.'
