"""
Strip Power Query connections from Excel before pushing to GitHub.
Reads the original file (with connections) and saves a clean copy (values only).
"""
import pandas as pd
from pathlib import Path
import sys

SRC = Path.home() / "Downloads" / "بيانات الاحصاءات الاقتصادية والاجتماعية.xlsx"
DST = Path(__file__).parent / "data" / "بيانات الاحصاءات الاقتصادية والاجتماعية.xlsx"

def clean():
    if not SRC.exists():
        print(f"خطأ: الملف غير موجود\n{SRC}")
        sys.exit(1)

    print("قراءة الملف الأصلي...")
    xls = pd.ExcelFile(SRC)

    DST.parent.mkdir(exist_ok=True)

    print("حفظ نسخة نظيفة (بيانات فقط، بدون اتصالات)...")
    with pd.ExcelWriter(DST, engine="openpyxl") as writer:
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df.to_excel(writer, sheet_name=sheet, index=False)

    print(f"تم الحفظ: {DST}")
    print(f"عدد الشيتات: {len(xls.sheet_names)}")

if __name__ == "__main__":
    clean()
