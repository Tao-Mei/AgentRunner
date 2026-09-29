param(
    [Parameter(Mandatory = $true)][string]$JobId,
    [Parameter(Mandatory = $true)][string]$EventId
)

$ErrorActionPreference = 'Stop'
if ($JobId -notmatch '^[A-Za-z0-9-]+$' -or $EventId -notmatch '^[A-Za-z0-9-]+$') {
    throw 'JobId and EventId must contain only letters, digits, or hyphens.'
}

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$stateDir = Join-Path $root 'probes\.probe-state\skill-claims'
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$claimPath = Join-Path $stateDir "$JobId--$EventId.json"

try {
    $stream = [System.IO.File]::Open($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $payload = [pscustomobject]@{ job_id = $JobId; event_id = $EventId; claimed_at_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json -Compress
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        $stream.Dispose()
    }
    [pscustomobject]@{ result = 'new'; job_id = $JobId; event_id = $EventId } | ConvertTo-Json -Compress
} catch [System.IO.IOException] {
    if (-not (Test-Path -LiteralPath $claimPath)) { throw }
    [pscustomobject]@{ result = 'duplicate'; job_id = $JobId; event_id = $EventId } | ConvertTo-Json -Compress
}
