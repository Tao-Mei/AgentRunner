# Run from the normal installation user's session, not a redirected sandbox.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallDir,
    [Parameter(Mandatory)][string]$DataRoot,
    [Parameter(Mandatory)][string]$SkillsRoot
)
$ErrorActionPreference = 'Stop'
foreach ($path in @($InstallDir, $DataRoot, $SkillsRoot)) {
    if (-not [IO.Path]::IsPathRooted($path) -or $path -match '^[A-Za-z]:[^\\/]' -or $path -match '[\r\n]') {
        throw 'Supply absolute installation, data and Skill paths from the actual user session.'
    }
}
$exe = Join-Path $InstallDir 'runner.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'The supplied installation has no runner.exe.' }
$sourceRoot = Join-Path (Split-Path $PSScriptRoot -Parent) '.agents\skills'
# Preflight both ownership markers before making changes.
foreach ($name in @('agent-runner', 'agent-runner-callback')) {
    if (-not (Test-Path -LiteralPath (Join-Path $SkillsRoot "$name\.agentrunner-owned"))) {
        throw "Refusing to overwrite a Skill not owned by the AgentRunner installer: $name"
    }
}
foreach ($name in @('agent-runner', 'agent-runner-callback')) {
    $target = Join-Path $SkillsRoot $name
    Copy-Item -LiteralPath (Join-Path $sourceRoot "$name\SKILL.md") -Destination (Join-Path $target 'SKILL.md')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'find-runner.ps1') -Destination (Join-Path $target 'scripts\find_runner.ps1')
    @('[Runner]', "Executable=$exe", "DataRoot=$DataRoot") | Set-Content -LiteralPath (Join-Path $target 'scripts\runner-location.ini') -Encoding UTF8
}
Write-Output 'Updated both installer-owned Skills and their local location manifests. Runner processes and task data were not changed.'
