@echo off
REM تحديث بيانات اللوحة من بوابة البيانات المفتوحة ورفعها للمستودع.
REM للتشغيل التلقائي: Task Scheduler > Create Basic Task > Daily > اختر هذا الملف.
cd /d "%~dp0"

python sync_data.py sync
if errorlevel 1 goto :done

git add data/live
git diff --staged --quiet && (echo لا توجد بيانات جديدة.) || (
    git commit -m "chore(data): تحديث تلقائي من بوابة البيانات المفتوحة"
    git push
)

:done
echo.
echo تم. اضغط أي مفتاح للإغلاق.
pause >nul
