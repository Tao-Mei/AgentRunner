$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$env:AGENTRUNNER_HOME = Join-Path $PSScriptRoot '.probe-state\control-home'

$short = (& python -m agentrunner exec --cwd $root -- pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'smoke_job.ps1')) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $short.status -ne 'COMPLETED' -or $short.exit_code -ne 0) {
    throw "Short exec failed: $($short | ConvertTo-Json -Compress)"
}

$long = (& python -m agentrunner exec --adaptive --grace-seconds 0.5 --cwd $root -- pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'smoke_long_job.ps1')) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $long.status -ne 'PROMOTED_TO_BACKGROUND') {
    throw "Adaptive promotion failed: $($long | ConvertTo-Json -Compress)"
}
$cancel = (& python -m agentrunner cancel $long.job_id) | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or -not $cancel.cancel_requested) {
    throw "Cancellation failed: $($cancel | ConvertTo-Json -Compress)"
}
Start-Sleep -Seconds 2
$final = (& python -m agentrunner show $long.job_id) | ConvertFrom-Json
if ($final.status -ne 'CANCELLED') {
    throw "Expected CANCELLED: $($final | ConvertTo-Json -Compress)"
}

[pscustomobject]@{
    short_status = $short.status
    short_exit_code = $short.exit_code
    adaptive_status = $long.status
    cancelled_job = $long.job_id
    final_status = $final.status
} | ConvertTo-Json
