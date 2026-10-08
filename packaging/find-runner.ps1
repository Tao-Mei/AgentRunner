# Resolve installation-owned paths without trusting sandbox environment folders.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
function Assert-AbsolutePath([string]$Path, [string]$Label) {
    if (-not $Path -or -not [IO.Path]::IsPathRooted($Path) -or $Path -match '^[A-Za-z]:[^\\/]') {
        throw "Invalid $Label path. Repair the installed Runner Skills."
    }
}
$manifest = Join-Path $PSScriptRoot 'runner-location.ini'
if (Test-Path -LiteralPath $manifest) {
    $settings = @{}
    foreach ($line in Get-Content -LiteralPath $manifest) {
        if ($line -match '^\s*(Executable|DataRoot)=(.*)$') {
            if ($settings.ContainsKey($matches[1])) { throw 'Duplicate Runner location setting. Repair the installed Skills.' }
            $settings[$matches[1]] = $matches[2].Trim()
        }
    }
    $runner = $settings['Executable']
    $dataRoot = $settings['DataRoot']
    Assert-AbsolutePath $runner 'executable'
    Assert-AbsolutePath $dataRoot 'data directory'
    if ([IO.Path]::GetFileName($runner) -ne 'runner.exe') { throw 'Invalid Runner executable name in location configuration.' }
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw "Registered Runner cannot be accessed at '$runner'. The installation may have moved or sandbox read access may be missing. Repair the Skills or request access; do not switch installations or resubmit blindly."
    }
} else {
    # Compatibility only. Known folders avoid env redirection, but may belong to
    # a sandbox account. Require manifest repair before using legacy discovery.
    $registeredRoot = $null
    try {
        $registeredRoot = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\AgentRunner').InstallLocation
    } catch { Write-Verbose "Installation registry unavailable: $($_.Exception.Message)" }
    $candidates = @()
    if ($registeredRoot) { $candidates += Join-Path $registeredRoot 'runner.exe' }
    $localRoot = [Environment]::GetFolderPath('LocalApplicationData')
    if ($localRoot) { $candidates += Join-Path $localRoot 'Programs\AgentRunner\runner.exe' }
    $found = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($found) {
        throw "Legacy Runner found at '$found', but its data directory is not registered. Repair/install the companion Skills from the normal user session before sandbox handoff."
    }
    throw 'Unable to locate AgentRunner in this execution environment. This does not prove it is uninstalled. Repair/install the companion Skills, or request sandbox access to the actual installation.'
}
# Explicit overrides are supported for intentional isolated runs only.
if ($env:AGENTRUNNER_HOME) {
    Assert-AbsolutePath $env:AGENTRUNNER_HOME 'AGENTRUNNER_HOME override'
} else {
    $env:AGENTRUNNER_HOME = $dataRoot
}
Write-Output $runner
