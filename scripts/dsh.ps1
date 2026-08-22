<#
.DESCRIPTION
  DeepSeek Harness launcher for the chaos-demo workspace.

  - Pins the harness version (see $DshVersion below).
  - Always starts from D:\chaos-demo, so the workspace root is deterministic.
  - Prefers a globally installed `dsh` (survives npx-cache cleanup);
    otherwise falls back to `npx --yes @deepseek-ai/dsh@<version>`.
  - Defaults to the web GUI when called with no arguments.

.EXAMPLE
  .\scripts\dsh.ps1                     # start the web GUI at the default port
.EXAMPLE
  .\scripts\dsh.ps1 web --port 3090     # start the web GUI on another port
.EXAMPLE
  .\scripts\dsh.ps1 --profile headless "run pytest and report results"
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$DshArgs
)

$ErrorActionPreference = 'Stop'

$DshVersion = '0.1.0-rc.6'
$Workspace  = 'D:\chaos-demo'

Set-Location -LiteralPath $Workspace

# Default to the web surface when the caller passes nothing.
if ($null -eq $DshArgs -or $DshArgs.Count -eq 0) {
    $DshArgs = @('web')
}

# 1) A global install (npm install -g @deepseek-ai/dsh@<version>) puts a
#    stable shim next to the other global tools on PATH.
$globalShim = Join-Path (npm config get prefix) 'dsh.cmd'
if (Test-Path -LiteralPath $globalShim) {
    & $globalShim @DshArgs
    exit $LASTEXITCODE
}

# 2) Fallback: pinned npx. --yes skips the interactive install prompt.
& npx.cmd --yes "@deepseek-ai/dsh@$DshVersion" @DshArgs
exit $LASTEXITCODE
