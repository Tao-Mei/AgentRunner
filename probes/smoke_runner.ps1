$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:AGENTRUNNER_HOME = Join-Path $PSScriptRoot '.probe-state\runner-home'

$raw = & python -m agentrunner run --cwd $root -- pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'smoke_job.ps1')
if ($LASTEXITCODE -ne 0) { throw "Submit failed: $raw" }
$submission = $raw | ConvertFrom-Json
if ($submission.status -ne 'ACCEPTED') { throw "Unexpected submission: $raw" }
Start-Sleep -Seconds 6
$job = (& python -m agentrunner show $submission.job_id) | ConvertFrom-Json
$logs = & python -m agentrunner logs $submission.job_id

[pscustomobject]@{
    submit_status = $submission.status
    job_id = $submission.job_id
    final_status = $job.status
    exit_code = $job.exit_code
    worker_pid = $job.worker_pid
    child_pid = $job.child_pid
    events = @($job.events).Count
    log_lines = @($logs)
} | ConvertTo-Json -Depth 4

if ($job.status -ne 'COMPLETED' -or $job.exit_code -ne 0 -or @($logs).Count -ne 2) { exit 1 }
