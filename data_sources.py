"""
طبقة مصادر البيانات الحية — Live data source layer.

Fetches datasets from the Saudi Open Data Portal (open.data.gov.sa) — or from any
direct file URL — normalises them into the same sheet shape the dashboard already
uses, and caches the result under ``data/live/``.

Design notes
------------
* The dashboard must never break because a remote source moved or went down.
  Every fetch is validated before it is allowed to touch the displayed data; a
  source that fails validation is recorded in the manifest and skipped, and the
  bundled Excel workbook keeps serving that sheet.
* The portal's API path has changed across portal versions, so the client tries a
  list of candidate patterns and remembers the one that answered.
* A source can skip the API entirely by giving ``resource_url`` — a direct link to
  a CSV/XLSX/JSON file. That path has no discovery step and is the most robust.
"""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:
    import requests
except ImportError:  # pragma: no cover - requests is declared in requirements.txt
    requests = None


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "sources.json"
LIVE_DIR = BASE_DIR / "data" / "live"
MANIFEST_PATH = LIVE_DIR / "manifest.json"

# Portal hosts, tried in order. The national portal is being migrated from
# open.data.gov.sa to od.data.gov.sa, so both are kept.
PORTAL_BASES = [
    "https://open.data.gov.sa",
    "https://od.data.gov.sa",
]

# Candidate API shapes. ``{id}`` is the dataset identifier, ``{q}`` a search term.
# The first pattern that returns parseable JSON wins and is cached in the manifest.
DATASET_PATTERNS = [
    "/data/api/v1/datasets?version=-1&dataset={id}",
    "/data/api/datasets?version=-1&dataset={id}",
    "/api/datasets/{id}",
    "/data/api/v1/datasets/{id}",
]
SEARCH_PATTERNS = [
    "/data/api/v1/datasets/search?version=-1&query={q}&page=0&size={size}",
    "/data/api/datasets/search?version=-1&query={q}&page=0&size={size}",
    "/api/datasets/search?q={q}&limit={size}",
]

TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".tsv"}
USER_AGENT = "economic-dashboard/1.0 (+data sync)"


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
@dataclass
class SourceSpec:
    """One configured dataset, bound to one sheet of the dashboard."""

    sheet: str
    label: str = ""
    publisher: str = ""
    enabled: bool = False
    dataset_id: str = ""
    resource_url: str = ""
    resource_match: str = ""
    date_column: str = "Date"
    column_map: dict = field(default_factory=dict)
    drop_columns: list = field(default_factory=list)
    merge_mode: str = "extend"  # "extend" keeps Excel history, "replace" overwrites
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "SourceSpec":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    @property
    def is_configured(self) -> bool:
        return bool(self.resource_url or self.dataset_id)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def load_config(path: Path | str = CONFIG_PATH) -> list[SourceSpec]:
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [SourceSpec.from_dict(item) for item in raw.get("sources", [])]


def save_config(specs: Iterable[SourceSpec], path: Path | str = CONFIG_PATH) -> None:
    path = Path(path)
    payload = {"sources": [s.to_dict() for s in specs]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────
# Portal client
# ──────────────────────────────────────────────
class PortalError(RuntimeError):
    pass


class OpenDataClient:
    """Minimal client for the Saudi Open Data Portal."""

    def __init__(self, api_key: str | None = None, bases: list[str] | None = None,
                 timeout: int = 60):
        if requests is None:
            raise PortalError("حزمة requests غير مثبتة — نفّذ: pip install requests")
        self.api_key = api_key or _api_key_from_env()
        self.bases = bases or list(PORTAL_BASES)
        self.timeout = timeout
        self.resolved_base: str | None = None
        self.resolved_pattern: str | None = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT,
                                     "Accept": "application/json, */*"})
        if self.api_key:
            # The portal has used both header names across versions; sending both
            # is harmless and saves a round of guessing.
            self.session.headers.update({"api_key": self.api_key,
                                         "Authorization": f"Bearer {self.api_key}"})

    # -- low level ----------------------------------------------------
    def _get(self, url: str, **kwargs) -> "requests.Response":
        return self.session.get(url, timeout=self.timeout, **kwargs)

    def _try_json(self, url: str) -> Any | None:
        try:
            resp = self._get(url)
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    # -- discovery ----------------------------------------------------
    def search(self, query: str, size: int = 10) -> list[dict]:
        """Search the portal for datasets matching ``query``."""
        from urllib.parse import quote

        errors = []
        for base in self.bases:
            for pattern in SEARCH_PATTERNS:
                url = base + pattern.format(q=quote(query), size=size)
                payload = self._try_json(url)
                if payload is None:
                    errors.append(url)
                    continue
                hits = _extract_records(payload)
                if hits:
                    self.resolved_base, self.resolved_pattern = base, pattern
                    return hits
        raise PortalError(
            "تعذّر الوصول لواجهة البحث في البوابة. المسارات التي جُرِّبت:\n  "
            + "\n  ".join(errors)
        )

    def get_dataset(self, dataset_id: str) -> dict:
        """Fetch metadata (including resources) for one dataset."""
        errors = []
        for base in self.bases:
            for pattern in DATASET_PATTERNS:
                url = base + pattern.format(id=dataset_id)
                payload = self._try_json(url)
                if payload is None:
                    errors.append(url)
                    continue
                records = _extract_records(payload)
                if records:
                    self.resolved_base, self.resolved_pattern = base, pattern
                    return records[0]
        raise PortalError(
            f"تعذّر جلب بيانات المجموعة {dataset_id}. المسارات التي جُرِّبت:\n  "
            + "\n  ".join(errors)
        )

    def list_resources(self, dataset_id: str) -> list[dict]:
        meta = self.get_dataset(dataset_id)
        return _extract_resources(meta)

    def pick_resource(self, dataset_id: str, match: str = "") -> dict:
        """Choose the tabular resource to download for a dataset."""
        resources = [r for r in self.list_resources(dataset_id) if _resource_url(r)]
        if not resources:
            raise PortalError(f"لا توجد ملفات قابلة للتنزيل في المجموعة {dataset_id}")
        if match:
            needle = match.lower()
            narrowed = [r for r in resources
                        if needle in json.dumps(r, ensure_ascii=False).lower()]
            if narrowed:
                resources = narrowed
        tabular = [r for r in resources
                   if _extension(_resource_url(r)) in TABULAR_EXTENSIONS]
        pool = tabular or resources
        # Prefer spreadsheets, then CSV, then whatever is left.
        priority = {".xlsx": 0, ".xls": 1, ".csv": 2, ".tsv": 3, ".json": 4}
        pool.sort(key=lambda r: priority.get(_extension(_resource_url(r)), 9))
        return pool[0]

    # -- download -----------------------------------------------------
    def download(self, url: str) -> tuple[bytes, str]:
        """Download a resource, returning ``(content, filename)``."""
        resp = self._get(url, headers={"Accept": "*/*"})
        if resp.status_code != 200:
            raise PortalError(f"فشل التنزيل ({resp.status_code}): {url}")
        return resp.content, _filename_from(resp, url)


def _api_key_from_env() -> str:
    """Read the portal API key from Streamlit secrets or the environment."""
    key = os.environ.get("OPEN_DATA_API_KEY", "")
    if key:
        return key
    try:  # pragma: no cover - only meaningful inside a Streamlit runtime
        import streamlit as st

        return st.secrets.get("open_data_api_key", "")
    except Exception:
        return ""


# ──────────────────────────────────────────────
# JSON shape helpers — the portal nests payloads differently per version
# ──────────────────────────────────────────────
def _extract_records(payload: Any) -> list[dict]:
    """Pull the list of dataset records out of an arbitrary portal response."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("datasets", "results", "content", "data", "items", "records", "result"):
        value = payload.get(key)
        if isinstance(value, list) and any(isinstance(v, dict) for v in value):
            return [v for v in value if isinstance(v, dict)]
        if isinstance(value, dict):
            nested = _extract_records(value)
            if nested:
                return nested
    # A bare dataset object (has an id and something name-like).
    if any(k in payload for k in ("id", "datasetId", "identifier")):
        return [payload]
    return []


def _extract_resources(meta: dict) -> list[dict]:
    for key in ("resources", "distribution", "files", "attachments", "datasetResources"):
        value = meta.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
    return []


def _resource_url(resource: dict) -> str:
    for key in ("downloadUrl", "download_url", "url", "accessUrl", "access_url",
                "path", "link", "fileUrl"):
        value = resource.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    return ""


def _extension(url: str) -> str:
    path = url.split("?")[0].split("#")[0]
    match = re.search(r"(\.[A-Za-z0-9]{1,5})$", path)
    return match.group(1).lower() if match else ""


def _filename_from(resp, url: str) -> str:
    disposition = resp.headers.get("content-disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", disposition)
    if match:
        return match.group(1)
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    if _extension(name):
        return name
    ctype = resp.headers.get("content-type", "").lower()
    if "spreadsheet" in ctype or "excel" in ctype:
        return name + ".xlsx"
    if "csv" in ctype:
        return name + ".csv"
    if "json" in ctype:
        return name + ".json"
    return name or "download"


# ──────────────────────────────────────────────
# Parsing and normalisation
# ──────────────────────────────────────────────
def parse_tabular(content: bytes, filename: str) -> pd.DataFrame:
    """Turn a downloaded file into a DataFrame, guessing by extension then content."""
    ext = _extension(filename)
    attempts = []
    if ext in (".xlsx", ".xls"):
        attempts = [_read_excel, _read_csv, _read_json]
    elif ext == ".json":
        attempts = [_read_json, _read_csv, _read_excel]
    else:
        attempts = [_read_csv, _read_excel, _read_json]

    errors = []
    for reader in attempts:
        try:
            df = reader(content)
        except Exception as exc:
            errors.append(f"{reader.__name__}: {exc}")
            continue
        if df is not None and not df.empty:
            return df
    raise PortalError(f"تعذّر قراءة الملف {filename}. المحاولات: {'; '.join(errors)}")


def _read_excel(content: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(content))


def _read_csv(content: bytes) -> pd.DataFrame:
    last = None
    for encoding in ("utf-8-sig", "utf-8", "cp1256", "latin-1"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=encoding, sep=sep)
            except Exception as exc:
                last = exc
                continue
            if df.shape[1] > 1:
                return df
    if last:
        raise last
    raise ValueError("تعذّر تحديد فاصل الأعمدة")


def _read_json(content: bytes) -> pd.DataFrame:
    payload = json.loads(content.decode("utf-8-sig"))
    if isinstance(payload, dict):
        for key in ("data", "records", "results", "content", "items", "rows"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    return pd.json_normalize(payload)


def normalize(df: pd.DataFrame, spec: SourceSpec) -> pd.DataFrame:
    """Apply the spec's renames, parse the date column and coerce numerics."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if spec.column_map:
        df = df.rename(columns={str(k).strip(): v for k, v in spec.column_map.items()})
    if spec.drop_columns:
        df = df.drop(columns=[c for c in spec.drop_columns if c in df.columns])

    df = df.loc[:, ~df.columns.duplicated()]
    df = df.dropna(how="all")
    df = df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed:")],
                 errors="ignore")

    # Resolve the date column *after* column_map, which may already have renamed it.
    date_col = spec.date_column or "Date"
    if date_col not in df.columns:
        mapped = spec.column_map.get(date_col)
        date_col = mapped if mapped in df.columns else "Date"
    if date_col in df.columns:
        if date_col != "Date":
            df = df.rename(columns={date_col: "Date"})
        df["Date"] = _parse_dates(df["Date"])
        df = df.dropna(subset=["Date"]).sort_values("Date")

    meta_cols = {"Date", "Note", "Year", "Month", "Quarter", "YearMonth", "MonthName"}
    for col in df.columns:
        if col in meta_cols or pd.api.types.is_numeric_dtype(df[col]):
            continue
        converted = pd.to_numeric(
            df[col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
        # Only accept the conversion if it did not destroy the column.
        if converted.notna().sum() >= df[col].notna().sum() * 0.8:
            df[col] = converted

    return df.reset_index(drop=True)


def _parse_dates(series: pd.Series) -> pd.Series:
    """Parse the portal's assorted period formats (2024, 2024-Q1, 2024-03, dates)."""
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.notna().mean() >= 0.8:
        return parsed

    text = series.astype(str).str.strip()

    quarters = text.str.extract(r"(\d{4})\s*[-/ ]?\s*[QqRr]?(\d)", expand=True)
    mask = quarters[0].notna() & quarters[1].notna() & quarters[1].isin(list("1234"))
    if mask.mean() >= 0.8:
        return pd.to_datetime(
            quarters[0] + "-" + ((quarters[1].astype(float) - 1) * 3 + 1)
            .astype("Int64").astype(str) + "-01",
            errors="coerce",
        )

    years = text.str.extract(r"^(\d{4})$", expand=False)
    if years.notna().mean() >= 0.8:
        return pd.to_datetime(years + "-01-01", errors="coerce")

    return parsed


def validate(live: pd.DataFrame, base: pd.DataFrame | None, spec: SourceSpec) -> None:
    """Raise if the fetched frame is not safe to show. Keeps a bad feed off-screen."""
    if live.empty:
        raise PortalError("الملف المُنزّل لا يحتوي على بيانات")
    if "Date" not in live.columns:
        raise PortalError(
            f"لا يوجد عمود تاريخ بعد التحويل (المتوقع: {spec.date_column}). "
            f"الأعمدة الموجودة: {list(live.columns)[:12]}"
        )
    if not pd.api.types.is_datetime64_any_dtype(live["Date"]):
        raise PortalError(
            f"تعذّر تحويل عمود التاريخ '{spec.date_column}' إلى تاريخ. "
            f"عيّنة من القيم: {live['Date'].head(3).tolist()}"
        )
    numeric = [c for c in live.select_dtypes(include="number").columns if c != "Date"]
    if not numeric:
        raise PortalError("لا توجد أعمدة رقمية بعد التحويل")
    if base is not None and not base.empty:
        shared = set(live.columns) & set(base.columns) - {"Date"}
        if not shared:
            raise PortalError(
                "أعمدة المصدر لا تطابق أعمدة الورقة الحالية — أضف column_map في "
                f"sources.json. أعمدة المصدر: {list(live.columns)[:12]}"
            )


def merge_sheet(base: pd.DataFrame | None, live: pd.DataFrame,
                mode: str = "extend") -> pd.DataFrame:
    """Combine the bundled sheet with freshly fetched rows."""
    if base is None or base.empty or mode == "replace":
        return live.reset_index(drop=True)
    if "Date" not in base.columns or "Date" not in live.columns:
        return live.reset_index(drop=True)

    combined = pd.concat([base, live], ignore_index=True)
    # Later rows win on a duplicate date, so live values override the workbook.
    combined = combined.drop_duplicates(subset="Date", keep="last")
    return combined.sort_values("Date").reset_index(drop=True)


# ──────────────────────────────────────────────
# Sync
# ──────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_manifest(live_dir: Path | str = LIVE_DIR) -> dict:
    path = Path(live_dir) / "manifest.json"
    if not path.exists():
        return {"sources": {}, "last_sync": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"sources": {}, "last_sync": None}


def _write_manifest(manifest: dict, live_dir: Path) -> None:
    live_dir.mkdir(parents=True, exist_ok=True)
    (live_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _latest_date(df: pd.DataFrame) -> str | None:
    if "Date" not in df.columns or not df["Date"].notna().any():
        return None
    if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
        return None
    return str(df["Date"].max().date())


def _cache_path(live_dir: Path, sheet: str) -> Path:
    safe = re.sub(r"[^\w؀-ۿ-]+", "_", sheet).strip("_")
    return live_dir / f"{safe}.csv"


def sync_source(spec: SourceSpec, client: OpenDataClient | None = None,
                base_sheets: dict | None = None,
                live_dir: Path | str = LIVE_DIR) -> dict:
    """Fetch one source and cache it. Returns a manifest entry (never raises)."""
    live_dir = Path(live_dir)
    entry: dict = {"sheet": spec.sheet, "label": spec.label, "checked_at": _now()}

    try:
        if not spec.enabled:
            raise PortalError("المصدر غير مُفعّل في sources.json")
        if not spec.is_configured:
            raise PortalError("لم يُحدَّد dataset_id ولا resource_url")

        url = spec.resource_url
        if not url:
            client = client or OpenDataClient()
            resource = client.pick_resource(spec.dataset_id, spec.resource_match)
            url = _resource_url(resource)
            entry["resource_title"] = str(
                resource.get("title") or resource.get("name") or ""
            )
        client = client or OpenDataClient()

        content, filename = client.download(url)
        raw = parse_tabular(content, filename)
        live = normalize(raw, spec)
        base = (base_sheets or {}).get(spec.sheet)
        validate(live, base, spec)

        path = _cache_path(live_dir, spec.sheet)
        live_dir.mkdir(parents=True, exist_ok=True)
        live.to_csv(path, index=False, encoding="utf-8-sig")

        entry.update(
            status="ok",
            source_url=url,
            filename=filename,
            rows=int(len(live)),
            columns=[str(c) for c in live.columns],
            cache_file=path.name,
            merge_mode=spec.merge_mode,
            updated_at=_now(),
            latest_date=_latest_date(live),
            error=None,
        )
    except Exception as exc:
        entry.update(status="error", error=str(exc))
    return entry


def sync_all(specs: Iterable[SourceSpec] | None = None,
             base_sheets: dict | None = None,
             live_dir: Path | str = LIVE_DIR,
             only: str | None = None) -> dict:
    """Sync every enabled source, updating the manifest. Failures are recorded."""
    live_dir = Path(live_dir)
    specs = list(specs if specs is not None else load_config())
    if only:
        specs = [s for s in specs if s.sheet == only]

    manifest = read_manifest(live_dir)
    manifest.setdefault("sources", {})

    client = None
    if any(s.enabled and not s.resource_url for s in specs):
        try:
            client = OpenDataClient()
        except PortalError:
            client = None

    for spec in specs:
        if not spec.enabled:
            manifest["sources"].pop(spec.sheet, None)
            continue
        entry = sync_source(spec, client=client, base_sheets=base_sheets,
                            live_dir=live_dir)
        previous = manifest["sources"].get(spec.sheet, {})
        if entry["status"] == "error" and previous.get("status") == "ok":
            # Keep the last good snapshot and its metadata; note why the refresh failed.
            previous = dict(previous)
            previous.update(checked_at=entry["checked_at"], error=entry["error"],
                            status="stale")
            entry = previous
        manifest["sources"][spec.sheet] = entry

    manifest["last_sync"] = _now()
    if client is not None and client.resolved_base:
        manifest["resolved_base"] = client.resolved_base
        manifest["resolved_pattern"] = client.resolved_pattern
    _write_manifest(manifest, live_dir)
    return manifest


def load_live_sheets(live_dir: Path | str = LIVE_DIR) -> dict:
    """Read cached live sheets. Returns ``{sheet_name: (DataFrame, merge_mode)}``."""
    live_dir = Path(live_dir)
    manifest = read_manifest(live_dir)
    out: dict = {}
    for sheet, entry in (manifest.get("sources") or {}).items():
        if entry.get("status") not in ("ok", "stale") or not entry.get("cache_file"):
            continue
        path = live_dir / entry["cache_file"]
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
        except Exception:
            continue
        if "Date" not in df.columns:
            continue  # not a usable series — leave the workbook sheet in place
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date")
        if df.empty:
            continue
        out[sheet] = (df.reset_index(drop=True), entry.get("merge_mode", "extend"))
    return out


def apply_live_data(base_sheets: dict, live_dir: Path | str = LIVE_DIR) -> dict:
    """Overlay cached live sheets onto the workbook sheets."""
    merged = dict(base_sheets)
    for sheet, (live, mode) in load_live_sheets(live_dir).items():
        base = merged.get(sheet)
        try:
            candidate = merge_sheet(base, live, mode)
        except Exception:
            continue  # a bad cache file must never take the dashboard down
        if candidate is None or candidate.empty:
            continue
        # Never trade a populated sheet for a thinner one unless asked to replace.
        if mode != "replace" and base is not None and len(candidate) < len(base):
            continue
        merged[sheet] = candidate
    return merged


def live_signature(live_dir: Path | str = LIVE_DIR) -> float:
    """Manifest mtime — used as a Streamlit cache key so refreshes take effect."""
    try:
        return (Path(live_dir) / "manifest.json").stat().st_mtime
    except OSError:
        return 0.0
