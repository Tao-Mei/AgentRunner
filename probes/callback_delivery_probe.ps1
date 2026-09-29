param(
    [Parameter(Mandatory = $true)][string]$ThreadId,
    [Parameter(Mandatory = $true)][string]$EventId,
    [switch]$InjectPreDispatchFailureOnce
)

$ErrorActionPreference = 'Stop'
if ($EventId -notmatch '^[A-Za-z0-9-]+$') { throw 'EventId must be alphanumeric or hyphen.' }

$stateDir = Join-Path $PSScriptRoot '.probe-state'
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$statePath = Join-Path $stateDir "$EventId.json"

function Save-State($state) {
    $tempPath = Join-Path $stateDir "$EventId.$PID.tmp"
    $state | ConvertTo-Json -Compress | Set-Content -LiteralPath $tempPath -Encoding utf8
    Move-Item -LiteralPath $tempPath -Destination $statePath -Force
}

if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    if ($state.status -eq 'accepted') {
        [pscustomobject]@{ result = 'duplicate_suppressed'; event_id = $EventId; queue_id = $state.queue_id } | ConvertTo-Json -Compress
        exit 0
    }
} else {
    $state = [pscustomobject]@{ event_id = $EventId; thread_id = $ThreadId; status = 'pending'; attempts = 0; queue_id = $null; last_error = $null }
    Save-State $state
}

for ($attempt = 1; $attempt -le 2; $attempt++) {
    $state.attempts = [int]$state.attempts + 1
    Save-State $state
    try {
        if ($InjectPreDispatchFailureOnce -and $attempt -eq 1) {
            throw 'INJECTED_PRE_DISPATCH_FAILURE'
        }
        $message = "AgentRunner 可靠性探针 ${EventId}：独立进程已完成一次重试与持久去重检查。收到后仅回复‘已收到 ${EventId}’，不要运行命令或继续开发。"
        $output = (& codex queue --thread $ThreadId --message $message 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) { throw "CODEX_QUEUE_FAILED: $output" }
        if ($output -notmatch 'Queued message ([0-9a-f-]+) for thread') { throw "AMBIGUOUS_QUEUE_RESPONSE: $output" }
        $state.queue_id = $Matches[1]
        $state.status = 'accepted'
        $state.last_error = $null
        Save-State $state
        [pscustomobject]@{ result = 'accepted'; event_id = $EventId; attempts = $state.attempts; queue_id = $state.queue_id } | ConvertTo-Json -Compress
        exit 0
    } catch {
        $state.last_error = $_.Exception.Message
        Save-State $state
        if ($state.last_error -notlike 'INJECTED_PRE_DISPATCH_FAILURE*') {
            [pscustomobject]@{ result = 'needs_reconciliation'; event_id = $EventId; attempts = $state.attempts; error = $state.last_error } | ConvertTo-Json -Compress
            exit 2
        }
        [pscustomobject]@{ result = 'injected_failure'; event_id = $EventId; attempts = $state.attempts } | ConvertTo-Json -Compress
    }
}

exit 1
