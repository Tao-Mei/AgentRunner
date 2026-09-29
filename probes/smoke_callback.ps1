param([Parameter(Mandatory = $true)][string]$ThreadId)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:AGENTRUNNER_HOME = Join-Path $PSScriptRoot '.probe-state\runner-home'

$raw = & python -m agentrunner run --cwd $root --callback-thread $ThreadId -- pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'smoke_job.ps1')
if ($LASTEXITCODE -ne 0) { throw "Submit failed: $raw" }
$submission = $raw | ConvertFrom-Json
if ($submission.status -ne 'ACCEPTED') { throw "Unexpected submission: $raw" }
Start-Sleep -Seconds 7
$job = (& python -m agentrunner show $submission.job_id) | ConvertFrom-Json

[pscustomobject]@{
    submit_status = $submission.status
    job_id = $submission.job_id
    event_id = $submission.event_id
    final_status = $job.status
    exit_code = $job.exit_code
    callback_status = $job.callback_status
    callback_message_id = $job.callback_message_id
    callback_error = $job.callback_error
} | ConvertTo-Json -Depth 3

if ($job.status -ne 'COMPLETED' -or $job.callback_status -ne 'SENT') { exit 1 }
