param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$name = 'AbleSci Assistant'
$script = Join-Path $PSScriptRoot 'app.py'
$arguments = '"{0}" --background' -f $script
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.Argument -ne $arguments) {
    throw 'A task for another copy of AbleSci Assistant already exists.'
}
if ($Remove) {
    if ($existing) { Unregister-ScheduledTask -TaskName $name -Confirm:$false }
    exit
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup.ps1 first.' }
$account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $PSScriptRoot
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $account
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger @($hourly,$logon) -Settings $settings -Principal $principal -Description 'AbleSci daily check-in and document request sync' -Force | Out-Null
Get-ScheduledTask -TaskName $name | Select-Object TaskName, State
