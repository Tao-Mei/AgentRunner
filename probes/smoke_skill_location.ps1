$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$source = Join-Path $repo 'packaging\find-runner.ps1'
foreach ($name in @('agent-runner', 'agent-runner-callback')) {
    if ((Get-FileHash $source).Hash -ne (Get-FileHash (Join-Path $repo ".agents\skills\$name\scripts\find_runner.ps1")).Hash) { throw 'Resolver copies drifted.' }
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('runner-location-test-' + [guid]::NewGuid())
$saved = @{}
foreach ($key in @('USERPROFILE', 'LOCALAPPDATA', 'AGENTRUNNER_HOME')) { $saved[$key] = [Environment]::GetEnvironmentVariable($key) }
try {
    New-Item -ItemType Directory -Path $root | Out-Null
    $exe = Join-Path $root 'custom 中文 install\runner.exe'
    New-Item -ItemType Directory -Path (Split-Path $exe) | Out-Null
    Set-Content -LiteralPath $exe -Value 'test placeholder; never executed'
    $data = Join-Path $root 'actual-user-data'
    $script = Join-Path $root 'find_runner.ps1'
    Copy-Item -LiteralPath $source -Destination $script
    $manifest = Join-Path $root 'runner-location.ini'
    $env:USERPROFILE = Join-Path $root 'sandbox-user'
    $env:LOCALAPPDATA = Join-Path $root 'sandbox-local'
    foreach ($encoding in @('Unicode', 'UTF8')) {
        @('[Runner]', "Executable=$exe", "DataRoot=$data") | Set-Content $manifest -Encoding $encoding
        $env:AGENTRUNNER_HOME = $null
        $result = & $script
        if ($result -ne $exe -or $env:AGENTRUNNER_HOME -ne $data) { throw 'Incorrect executable/data under redirected environment.' }
        if (Test-Path $data) { throw 'Resolver created a data directory.' }
    }
    $env:AGENTRUNNER_HOME = Join-Path $root 'intentional-isolation'
    $null = & $script
    if ($env:AGENTRUNNER_HOME -ne (Join-Path $root 'intentional-isolation')) { throw 'Explicit override lost.' }
    $env:AGENTRUNNER_HOME = 'relative-data'
    try { $null = & $script; throw 'Unexpected success' } catch { if ($_.Exception.Message -notlike 'Invalid AGENTRUNNER_HOME*') { throw } }
    $env:AGENTRUNNER_HOME = $null
    @('[Runner]', "Executable=$root\missing\runner.exe", "DataRoot=$data") | Set-Content $manifest
    try { $null = & $script; throw 'Unexpected success' } catch { if ($_.Exception.Message -notlike 'Registered Runner cannot be accessed*') { throw } }
    @('[Runner]', 'Executable=relative\runner.exe', "DataRoot=$data") | Set-Content $manifest
    try { $null = & $script; throw 'Unexpected success' } catch { if ($_.Exception.Message -notlike 'Invalid executable*') { throw } }
    @('[Runner]', "Executable=$exe", "DataRoot=$data", "DataRoot=$data") | Set-Content $manifest
    try { $null = & $script; throw 'Unexpected success' } catch { if ($_.Exception.Message -notlike 'Duplicate Runner*') { throw } }
    Remove-Item -LiteralPath $manifest
    try { $null = & $script; throw 'Unexpected success' } catch { if ($_.Exception.Message -notmatch 'Legacy Runner found|Unable to locate AgentRunner') { throw } }
    'PASS: resolver copies, redirected environment, Unicode/custom paths, canonical data root, overrides, invalid/stale/missing manifests.'
} finally {
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key]) }
    if ((Split-Path $root -Leaf) -like 'runner-location-test-*') { Remove-Item -LiteralPath $root -Recurse -Force }
}
