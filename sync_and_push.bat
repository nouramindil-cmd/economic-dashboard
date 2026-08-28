@echo off
chcp 65001 >nul
REM ============================================================
REM  تحديث بيانات لوحة المؤشرات من بوابة البيانات المفتوحة.
REM  شغّل هذا الملف بالضغط عليه مرتين. لا يحتاج أي إعداد يدوي.
REM  للتشغيل التلقائي يومياً:
REM    Task Scheduler > Create Basic Task > Daily > اختر هذا الملف.
REM ============================================================
cd /d "%~dp0"

echo.
echo [1/3] تجهيز المتطلبات...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo تعذّر تثبيت المتطلبات. تأكد من تثبيت Python.
    goto :done
)

echo.
echo [2/3] البحث عن المؤشرات غير المضبوطة في البوابة...
python sync_data.py auto

echo.
echo [3/3] تحديث البيانات...
python sync_data.py sync

echo.
echo رفع التحديثات...
git add data/live sources.json
git diff --staged --quiet && (
    echo لا توجد بيانات جديدة.
) || (
    git commit -m "chore(data): تحديث تلقائي من بوابة البيانات المفتوحة"
    git push
)

:done
echo.
echo تم. اضغط أي مفتاح للإغلاق.
pause >nul
