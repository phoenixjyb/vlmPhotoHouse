param([Parameter(Mandatory=$true)][string]$RollbackScript)
# Synthetic command doubles only: no real scheduled task or process is changed.
$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('feed-rollback-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root|Out-Null
$global:PhotoHouseRollbackTestState=@{root=$root;stops=@();sets=@();wrongOwner=$false;processPresent=$false}
function Get-ScheduledTask {param($TaskName)
    $path=if($global:PhotoHouseRollbackTestState.wrongOwner){'other.py'}else{Join-Path $global:PhotoHouseRollbackTestState.root 'scripts\home_feed_background.py'}
    [pscustomobject]@{Actions=@([pscustomobject]@{Execute='C:\synthetic\venv\Scripts\pythonw.exe';Arguments='-I -B "'+$path+'"'})}
}
function New-ScheduledTaskAction {param($Execute,$Argument,$WorkingDirectory)
    [pscustomobject]@{Execute=$Execute;Arguments=$Argument;WorkingDirectory=$WorkingDirectory}
}
function Stop-ScheduledTask {param($TaskName) $global:PhotoHouseRollbackTestState.stops+= $TaskName}
function Set-ScheduledTask {param($TaskName,$Action) $global:PhotoHouseRollbackTestState.sets+= [pscustomobject]@{name=$TaskName;action=$Action}}
function Start-Sleep {param($Seconds)}
function Get-Process {param($Id,$ErrorAction) if($global:PhotoHouseRollbackTestState.processPresent){[pscustomobject]@{Id=$Id}}}
try {
    foreach($name in @('PhotoHouse-HomeFeed-Synthetic','PhotoHouse-HomeCatalog-V2-Canary')){
        '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Actions><Exec><Command>C:\synthetic\venv\Scripts\python.exe</Command><Arguments>-B original.py</Arguments><WorkingDirectory>C:\synthetic</WorkingDirectory></Exec></Actions></Task>' | Set-Content (Join-Path $root ($name+'.before.xml'))
    }
    foreach($kind in @('v1','v2')){
        New-Item -ItemType Directory -Path (Join-Path $root ($kind+'-logs'))|Out-Null
        '{"pid":999999}'|Set-Content (Join-Path $root ($kind+'-logs\process.json'))
    }
    $global:PhotoHouseRollbackTestState.wrongOwner=$true;$caught=$false
    try{& $RollbackScript -Stage $root}catch{$caught=$true}
    if(-not $caught -or $global:PhotoHouseRollbackTestState.stops.Count -ne 0){throw 'Ownership guard failed'}
    $global:PhotoHouseRollbackTestState.wrongOwner=$false;$global:PhotoHouseRollbackTestState.processPresent=$true;$caught=$false
    try{& $RollbackScript -Stage $root}catch{$caught=$true}
    if(-not $caught -or $global:PhotoHouseRollbackTestState.sets.Count -ne 0){throw 'Live-process guard failed'}
    $global:PhotoHouseRollbackTestState.processPresent=$false;$global:PhotoHouseRollbackTestState.stops=@();$global:PhotoHouseRollbackTestState.sets=@()
    & $RollbackScript -Stage $root|Out-Null
    if($global:PhotoHouseRollbackTestState.stops.Count -ne 2 -or $global:PhotoHouseRollbackTestState.sets.Count -ne 2){throw 'Expected exact two task actions'}
    foreach($s in $global:PhotoHouseRollbackTestState.sets){if($s.action.Execute -ne 'C:\synthetic\venv\Scripts\python.exe' -or $s.action.Arguments -ne '-B original.py'){throw 'Saved action mismatch'}}
    Write-Output 'PASS: ownership refusal, live-process refusal, two saved actions restored without restart (synthetic).'
} finally {Remove-Item $root -Recurse -Force;Remove-Variable PhotoHouseRollbackTestState -Scope Global}
