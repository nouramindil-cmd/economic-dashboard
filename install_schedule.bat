@echo off
chcp 65001 >nul
REM ============================================================
REM  يسجّل مهمة أسبوعية في ويندوز لتحديث بيانات اللوحة.
REM  شغّله مرة واحدة فقط (بالضغط عليه مرتين).
REM  للحذف لاحقاً: schtasks /Delete /TN "تحديث لوحة المؤشرات" /F
REM ============================================================
cd /d "%~dp0"
set "TASKNAME=تحديث لوحة المؤشرات"
set "TARGET=%~dp0sync_and_push.bat"

if not exist "%TARGET%" (
    echo لم أجد sync_and_push.bat بجوار هذا الملف.
    echo ضع الملفين في نفس المجلد ثم أعد المحاولة.
    goto :done
)

echo تسجيل مهمة أسبوعية: كل يوم أحد الساعة 8 صباحاً.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$bat = '%TARGET%';" ^
  "$dir = Split-Path $bat;" ^
  "$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"' + $bat + '\"') -WorkingDirectory $dir;" ^
  "$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 8am;" ^
  "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "Register-ScheduledTask -TaskName '%TASKNAME%' -Action $action -Trigger $trigger -Settings $settings -Description 'تحديث بيانات لوحة المؤشرات من المصادر الحكومية' -Force | Out-Null;" ^
  "Write-Host 'تم تسجيل المهمة بنجاح.'"

if errorlevel 1 (
    echo.
    echo تعذّر التسجيل. جرّب تشغيل هذا الملف كمسؤول:
    echo   اضغط عليه بزر الفأرة الأيمن ثم "Run as administrator".
    goto :done
)

echo.
echo الخيار "شغّل عند أول فرصة إذا فاتت" مُفعّل، فلو كان الجهاز مغلقاً
echo وقت الموعد ستعمل المهمة تلقائياً عند تشغيله.
echo.
echo لتشغيلها الآن للتجربة:
echo   schtasks /Run /TN "%TASKNAME%"

:done
echo.
echo اضغط أي مفتاح للإغلاق.
pause >nul
