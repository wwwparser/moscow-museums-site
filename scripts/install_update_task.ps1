param([string]$Time = '07:30')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = (Get-Command python).Source
$scriptPath = Join-Path $PSScriptRoot 'run_scheduled_update.ps1'
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $scriptPath + '" -PythonPath "' + $pythonPath + '"'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName 'MoscowMuseums-DailyUpdate' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Daily museum calendars and Telegram; Sunday full websites and admission refresh, followed by GitHub Pages publishing.' -Force | Select-Object TaskName,State
Get-ScheduledTaskInfo -TaskName 'MoscowMuseums-DailyUpdate' | Select-Object NextRunTime,LastTaskResult
