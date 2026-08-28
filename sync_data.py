#!/usr/bin/env python3
"""
أداة مزامنة البيانات مع بوابة البيانات المفتوحة.

    python sync_data.py discover "الناتج المحلي الإجمالي"   # ابحث عن مجموعة بيانات
    python sync_data.py inspect <dataset_id>                # اعرض ملفات المجموعة
    python sync_data.py preview <dataset_id|url>            # نزّل واعرض الأعمدة
    python sync_data.py sync [--only SHEET]                 # حدّث البيانات
    python sync_data.py status                              # حالة المصادر

`discover` و `inspect` و `preview` تُستخدم مرة واحدة لتعبئة sources.json،
بعدها يكفي `sync` (أو مهمة GitHub Actions المجدولة) لتحديث البيانات تلقائياً.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

import data_sources as ds

BASE_DIR = Path(__file__).parent
EXCEL_PATH = BASE_DIR / "data" / "بيانات الاحصاءات الاقتصادية والاجتماعية.xlsx"


def load_base_sheets() -> dict:
    """Load the bundled workbook, used to validate that fetched columns line up."""
    if not EXCEL_PATH.exists():
        return {}
    try:
        xls = pd.ExcelFile(EXCEL_PATH)
        return {s: pd.read_excel(xls, sheet_name=s) for s in xls.sheet_names}
    except Exception as exc:
        print(f"تحذير: تعذّرت قراءة ملف الإكسل ({exc})", file=sys.stderr)
        return {}


def _get(record: dict, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, dict):
            value = value.get("ar") or value.get("en") or ""
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def cmd_discover(args) -> int:
    client = ds.OpenDataClient()
    try:
        hits = client.search(args.query, size=args.limit)
    except ds.PortalError as exc:
        print(f"خطأ: {exc}", file=sys.stderr)
        return 1
    print(f"المسار المستخدم: {client.resolved_base}{client.resolved_pattern}\n")
    for i, hit in enumerate(hits, 1):
        title = _get(hit, "title", "name", "titleAr", "datasetTitle") or "(بدون عنوان)"
        ident = _get(hit, "id", "datasetId", "identifier", "uuid")
        org = _get(hit, "organization", "publisher", "organizationName")
        print(f"{i}. {title}")
        print(f"   dataset_id : {ident}")
        if org:
            print(f"   الجهة      : {org}")
        resources = ds._extract_resources(hit)
        for res in resources[:5]:
            print(f"   ملف        : {_get(res, 'title', 'name') or '-'} "
                  f"→ {ds._resource_url(res) or '-'}")
        print()
    if not hits:
        print("لا توجد نتائج.")
    return 0


def cmd_inspect(args) -> int:
    client = ds.OpenDataClient()
    try:
        meta = client.get_dataset(args.dataset_id)
    except ds.PortalError as exc:
        print(f"خطأ: {exc}", file=sys.stderr)
        return 1
    print(f"العنوان: {_get(meta, 'title', 'name') or '-'}\n")
    resources = ds._extract_resources(meta)
    if not resources:
        print("لا توجد ملفات مرفقة. المفاتيح المتاحة:", sorted(meta.keys()))
        return 1
    for i, res in enumerate(resources, 1):
        print(f"{i}. {_get(res, 'title', 'name') or '(بدون اسم)'}")
        print(f"   resource_url: {ds._resource_url(res) or '-'}")
        fmt = _get(res, "format", "mimeType", "extension")
        if fmt:
            print(f"   الصيغة      : {fmt}")
    return 0


def cmd_preview(args) -> int:
    """Download a dataset/URL and print its columns — what you need for column_map."""
    client = ds.OpenDataClient()
    target = args.target
    try:
        if target.startswith("http"):
            url = target
        else:
            url = ds._resource_url(client.pick_resource(target, args.match))
        content, filename = client.download(url)
        df = ds.parse_tabular(content, filename)
    except ds.PortalError as exc:
        print(f"خطأ: {exc}", file=sys.stderr)
        return 1

    print(f"الملف: {filename}   |   الأبعاد: {df.shape[0]} صف × {df.shape[1]} عمود\n")
    print("الأعمدة:")
    for col in df.columns:
        print(f"  - {col}")
    print("\nأول ٥ صفوف:")
    with pd.option_context("display.max_columns", 20, "display.width", 200):
        print(df.head())

    if args.sheet:
        base = load_base_sheets().get(args.sheet)
        if base is None:
            print(f"\nالورقة {args.sheet} غير موجودة في ملف الإكسل.")
        else:
            missing = [c for c in base.columns if c not in df.columns
                       and not str(c).startswith("Unnamed:")]
            print(f"\nأعمدة الورقة {args.sheet} غير الموجودة في المصدر "
                  f"(تحتاج column_map):")
            for col in missing:
                print(f"  - {col}")
    return 0


def cmd_sync(args) -> int:
    specs = ds.load_config()
    if not specs:
        print("لا يوجد ملف sources.json أو أنه فارغ.", file=sys.stderr)
        return 1
    enabled = [s for s in specs if s.enabled and (not args.only or s.sheet == args.only)]
    if not enabled:
        print("لا توجد مصادر مُفعّلة. فعّل مصدراً في sources.json (enabled: true).")
        return 0

    manifest = ds.sync_all(specs, base_sheets=load_base_sheets(), only=args.only)
    failures = 0
    for spec in enabled:
        entry = manifest["sources"].get(spec.sheet, {})
        status = entry.get("status", "missing")
        label = spec.label or spec.sheet
        if status == "ok":
            print(f"✅ {label}: {entry.get('rows')} صف "
                  f"(حتى {entry.get('latest_date') or '-'})")
        elif status == "stale":
            failures += 1
            print(f"⚠️  {label}: فشل التحديث، أُبقيت النسخة السابقة — {entry.get('error')}")
        else:
            failures += 1
            print(f"❌ {label}: {entry.get('error')}")
    print(f"\nآخر مزامنة: {manifest.get('last_sync')}")
    return 1 if (failures and args.strict) else 0


def cmd_status(args) -> int:
    manifest = ds.read_manifest()
    specs = {s.sheet: s for s in ds.load_config()}
    print(f"آخر مزامنة: {manifest.get('last_sync') or 'لم تتم بعد'}\n")
    entries = manifest.get("sources") or {}
    if not entries:
        print("لا توجد مصادر مُزامنة. راجع sources.json.")
        return 0
    icons = {"ok": "✅", "stale": "⚠️ ", "error": "❌"}
    for sheet, entry in entries.items():
        label = entry.get("label") or specs.get(sheet, None) and specs[sheet].label or sheet
        print(f"{icons.get(entry.get('status'), '•')} {label} [{sheet}]")
        print(f"    الحالة   : {entry.get('status')}")
        print(f"    الصفوف   : {entry.get('rows', '-')}   حتى: {entry.get('latest_date') or '-'}")
        print(f"    التحديث  : {entry.get('updated_at') or '-'}")
        if entry.get("error"):
            print(f"    الخطأ    : {entry['error']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="مزامنة بيانات لوحة المؤشرات مع بوابة البيانات المفتوحة")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("discover", help="ابحث عن مجموعات بيانات في البوابة")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("inspect", help="اعرض ملفات مجموعة بيانات")
    p.add_argument("dataset_id")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("preview", help="نزّل مصدراً واعرض أعمدته")
    p.add_argument("target", help="dataset_id أو رابط ملف مباشر")
    p.add_argument("--match", default="", help="كلمة لتصفية الملفات داخل المجموعة")
    p.add_argument("--sheet", default="", help="قارن الأعمدة مع ورقة في ملف الإكسل")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("sync", help="حدّث البيانات من المصادر المُفعّلة")
    p.add_argument("--only", default="", help="اسم ورقة واحدة فقط")
    p.add_argument("--strict", action="store_true",
                   help="أرجع رمز خطأ إذا فشل أي مصدر")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("status", help="اعرض حالة المصادر")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
