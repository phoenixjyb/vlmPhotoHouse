# Native Windows PowerShell check. Does not load app, models or runtime configuration.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$cases = @(
    @{Path='scripts/start-dev.ps1'; Args=@{Port=8002; Host='0.0.0.0'; Reload=$true}},
    @{Path='scripts/start-dev-multiproc.ps1'; Args=@{KillExisting=$true; TailscaleAccess=$true; Gpu=$true}},
    @{Path='scripts/start-photohouse-api.ps1'; Args=@{Detached=$true; NoAutoMigrate=$true}},
    @{Path='scripts/run-runtime-canary.ps1'; Args=@{}},
    @{Path='tools/morning-intake-and-start.ps1'; Args=@{PreflightOnly=$true}}
)
foreach ($case in $cases) {
    $tokens=$null; $parseErrors=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $root $case.Path), [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count -ne 0) { throw 'Retired launcher parse failure' }
    # Refuse execution unless the entire executable body is one literal throw.
    if ($ast.BeginBlock -or $ast.ProcessBlock -or $ast.DynamicParamBlock -or
        $ast.EndBlock.Statements.Count -ne 1 -or
        $ast.EndBlock.Statements[0] -isnot [System.Management.Automation.Language.ThrowStatementAst] -or
        $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.CommandAst]}, $true).Count -ne 0) {
        throw 'Retired launcher has executable side effects; invocation refused'
    }
    $arguments=$case.Args
    try { & ($ast.GetScriptBlock()) @arguments; throw 'Launcher returned without refusal' }
    catch {
        if ($_.Exception.Message -notlike 'Legacy combined launcher retired.*No runtime action was performed.') { throw }
    }
}
Write-Output 'PASS: five legacy PowerShell launchers parse and refuse before runtime work.'
