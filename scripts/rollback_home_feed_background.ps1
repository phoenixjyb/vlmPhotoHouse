param([Parameter(Mandatory=$true)][string]$Stage)
# Explicit operator rollback only. Stop these owned tasks, restore saved actions,
# and leave them stopped. Do not automatically relaunch console Python.
$ErrorActionPreference='Stop'
$names=@('PhotoHouse-HomeFeed-Synthetic','PhotoHouse-HomeCatalog-V2-Canary')
$launcher=Join-Path $Stage 'scripts\home_feed_background.py'
$saved=@{}
foreach($name in $names){
    $task=Get-ScheduledTask -TaskName $name
    if(@($task.Actions).Count -ne 1 -or
       -not $task.Actions.Arguments.Contains('"'+$launcher+'"') -or
       -not $task.Actions.Execute.EndsWith('\venv\Scripts\pythonw.exe')){
        throw 'Task ownership changed; inspect before rollback'
    }
    [xml]$xml=Get-Content (Join-Path $Stage ($name+'.before.xml')) -Raw
    $exec=@($xml.Task.Actions.Exec)
    if($exec.Count -ne 1){throw 'Unexpected saved action'}
    $saved[$name]=New-ScheduledTaskAction -Execute ([string]$exec[0].Command) `
        -Argument ([string]$exec[0].Arguments) -WorkingDirectory ([string]$exec[0].WorkingDirectory)
}
foreach($name in $names){Stop-ScheduledTask -TaskName $name}
Start-Sleep -Seconds 3
foreach($kind in @('v1','v2')){
    $receipt=Get-Content (Join-Path $Stage ($kind+'-logs\process.json')) -Raw|ConvertFrom-Json
    if(Get-Process -Id $receipt.pid -ErrorAction SilentlyContinue){
        throw 'Owned process still present; do not restore/relaunch yet'
    }
}
foreach($name in $names){Set-ScheduledTask -TaskName $name -Action $saved[$name]|Out-Null}
Write-Output 'Saved task actions restored; feeds remain stopped. Publications/configurations unchanged.'
