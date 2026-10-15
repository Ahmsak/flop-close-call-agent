param([Parameter(ValueFromRemainingArguments=$true)][string[]]$AgentArguments)
$ErrorActionPreference = 'Stop'
$AgentPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $AgentPython)) {
    $AgentPython = (Get-Command python -ErrorAction Stop).Source
}
if (-not $AgentArguments) { $AgentArguments = @('doctor') }
if ($AgentArguments[0] -eq 'automation-demo') {
    $DemoArguments = @($AgentArguments | Select-Object -Skip 1)
    & $AgentPython (Join-Path $PSScriptRoot 'automation_demo.py') @DemoArguments
    exit $LASTEXITCODE
}
if ($AgentArguments[0] -eq 'mission') {
    $MissionArguments = @($AgentArguments | Select-Object -Skip 1)
    & $AgentPython (Join-Path $PSScriptRoot 'mission.py') @MissionArguments
    exit $LASTEXITCODE
}
& $AgentPython (Join-Path $PSScriptRoot 'agent.py') @AgentArguments
exit $LASTEXITCODE
