$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:AGENTRUNNER_HOME = Join-Path $PSScriptRoot '.probe-state\runner-home'

$raw = & python -m agentrunner run --cwd $root -- pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'smoke_failure_job.ps1')
if ($LASTEXITCODE -ne 0) { throw "Submit failed: $raw" }
$submission = $raw | ConvertFrom-Json
Start-Sleep -Seconds 2
$job = (& python -m agentrunner show $submission.job_id) | ConvertFrom-Json
$stderr = & python -m agentrunner logs $submission.job_id --stream stderr

[pscustomobject]@{
    submit_status = $submission.status
    job_id = $submission.job_id
    final_status = $job.status
    exit_code = $job.exit_code
    stderr = @($stderr)
} | ConvertTo-Json -Depth 3

if ($job.status -ne 'FAILED' -or $job.exit_code -ne 7 -or $stderr -notcontains 'smoke-error') { exit 1 }
