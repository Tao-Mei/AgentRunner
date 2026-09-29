param([Parameter(Mandatory = $true)][string]$EventId)

$ErrorActionPreference = 'Stop'
if ($EventId -notmatch '^[A-Za-z0-9-]+$') { throw 'Invalid EventId.' }

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$runDir = Join-Path $root "probes\.probe-state\inflight\$EventId"
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$start = [DateTime]::UtcNow
$start.ToString('o') | Set-Content -LiteralPath (Join-Path $runDir 'started.txt') -Encoding utf8

for ($tick = 1; $tick -le 12; $tick++) {
    Add-Content -LiteralPath (Join-Path $runDir 'ticks.txt') -Value $tick -Encoding utf8
    Start-Sleep -Seconds 1
}

$end = [DateTime]::UtcNow
$end.ToString('o') | Set-Content -LiteralPath (Join-Path $runDir 'completed.txt') -Encoding utf8
$queuedPath = Join-Path $runDir 'duplicate_queued.txt'
$queued = if (Test-Path -LiteralPath $queuedPath) { [DateTime]::Parse((Get-Content -LiteralPath $queuedPath -Raw).Trim()).ToUniversalTime() } else { $null }
$tickCount = @(Get-Content -LiteralPath (Join-Path $runDir 'ticks.txt')).Count

[pscustomobject]@{
    event_id = $EventId
    completed = $true
    tick_count = $tickCount
    started_utc = $start.ToString('o')
    completed_utc = $end.ToString('o')
    duplicate_queued_utc = if ($queued) { $queued.ToString('o') } else { $null }
    queue_during_run = [bool]($queued -and $queued -ge $start -and $queued -le $end)
} | ConvertTo-Json -Compress
