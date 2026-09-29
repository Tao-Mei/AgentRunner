param(
    [Parameter(Mandatory = $true)][string]$ThreadId,
    [Parameter(Mandatory = $true)][string]$JobId,
    [Parameter(Mandatory = $true)][string]$EventId
)

$ErrorActionPreference = 'Stop'
$runDir = Join-Path $PSScriptRoot ".probe-state\inflight\$EventId"
$startPath = Join-Path $runDir 'started.txt'
$deadline = [DateTime]::UtcNow.AddSeconds(60)
while (-not (Test-Path -LiteralPath $startPath)) {
    if ([DateTime]::UtcNow -gt $deadline) { throw 'First callback did not start the in-flight command within 60 seconds.' }
    Start-Sleep -Milliseconds 250
}

Start-Sleep -Seconds 1
$message = '$agent-runner-callback AGENTRUNNER_CALLBACK_V1 job_id=' + $JobId + ' event_id=' + $EventId + ' probe=inflight'
$output = (& codex queue --thread $ThreadId --message $message 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $output -notmatch 'Queued message ([0-9a-f-]+) for thread') { throw "Duplicate callback queue failed: $output" }
[DateTime]::UtcNow.ToString('o') | Set-Content -LiteralPath (Join-Path $runDir 'duplicate_queued.txt') -Encoding utf8
$Matches[1] | Set-Content -LiteralPath (Join-Path $runDir 'duplicate_queue_id.txt') -Encoding utf8
