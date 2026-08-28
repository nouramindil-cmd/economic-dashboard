import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

import data_sources

# ──────────────────────────────────────────────
# Page Config (must be first Streamlit command)
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="لوحة المؤشرات الاقتصادية والاجتماعية",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# Authentication
# ──────────────────────────────────────────────
def check_password():
    """Simple password protection."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("<div style='max-width:400px;margin:120px auto;text-align:center;'>"
                    "<h2>لوحة المؤشرات الاقتصادية</h2></div>", unsafe_allow_html=True)
        st.text_input("كلمة المرور", type="password",
                      on_change=password_entered, key="password")
        return False
    if not st.session_state["password_correct"]:
        st.text_input("كلمة المرور", type="password",
                      on_change=password_entered, key="password")
        st.error("كلمة المرور غير صحيحة")
        return False
    return True

if not check_password():
    st.stop()

# ──────────────────────────────────────────────
# Professional CSS - Formal Report Style
# ──────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap');

    * { font-family: 'Tajawal', sans-serif; }

    /* Hide default Streamlit elements for cleaner look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Main header */
    .main-header {
        background: linear-gradient(135deg, #1B3A5C 0%, #2C5F8A 100%);
        color: white;
        padding: 24px 32px;
        border-radius: 12px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .main-header h1 { font-size: 1.6rem; font-weight: 700; margin: 0; color: white; }
    .main-header .subtitle { font-size: 0.85rem; color: #b8d4f0; margin-top: 4px; }
    .main-header .date-badge {
        background: rgba(255,255,255,0.15);
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 0.8rem;
        color: #e0ecf8;
    }

    /* KPI Cards - Formal Style */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 18px 20px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        transition: box-shadow 0.2s;
    }
    .kpi-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
    .kpi-label { font-size: 0.8rem; color: #6b7280; font-weight: 500; margin-bottom: 6px; }
    .kpi-value { font-size: 1.6rem; font-weight: 700; color: #1B3A5C; margin: 4px 0; }
    .kpi-delta { font-size: 0.78rem; font-weight: 500; margin-top: 4px; }
    .kpi-delta.up { color: #059669; }
    .kpi-delta.down { color: #dc2626; }
    .kpi-delta.neutral { color: #d97706; }

    /* Section titles */
    .section-title {
        font-size: 1.15rem;
        font-weight: 700;
        color: #1B3A5C;
        margin: 28px 0 14px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #e5e7eb;
    }

    /* Page title */
    .page-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #1B3A5C;
        margin-bottom: 4px;
    }
    .page-subtitle {
        color: #6b7280;
        font-size: 0.85rem;
        margin-bottom: 20px;
    }

    /* Tables */
    .styled-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
        margin: 16px 0;
    }
    .styled-table thead th {
        background: #1B3A5C;
        color: white;
        padding: 10px 14px;
        text-align: center;
        font-weight: 600;
        font-size: 0.8rem;
    }
    .styled-table tbody td {
        padding: 8px 14px;
        text-align: center;
        border-bottom: 1px solid #e5e7eb;
        color: #374151;
    }
    .styled-table tbody tr:nth-child(even) { background: #f9fafb; }
    .styled-table tbody tr:hover { background: #eff6ff; }

    /* Filter bar */
    .filter-bar {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 20px;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid #e2e8f0;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 0.9rem;
        padding: 6px 0;
    }

    /* Footer */
    .report-footer {
        text-align: center;
        color: #9ca3af;
        font-size: 0.75rem;
        padding: 20px 0;
        border-top: 1px solid #e5e7eb;
        margin-top: 40px;
    }

    /* Divider */
    .divider {
        border: none;
        border-top: 1px solid #e5e7eb;
        margin: 20px 0;
    }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────
# Path to data file - reads from data/ folder (works locally and on Streamlit Cloud)
EXCEL_PATH = Path(__file__).parent / "data" / "بيانات الاحصاءات الاقتصادية والاجتماعية.xlsx"


def _get_file_mtime():
    """Get file modification time to detect changes."""
    try:
        return EXCEL_PATH.stat().st_mtime
    except OSError:
        return 0


@st.cache_data(ttl=60)
def load_all_data(_file_mtime, _live_mtime=0.0):
    """Load data. The mtime args force a reload when the file or live cache changes."""
    xls = pd.ExcelFile(EXCEL_PATH)
    data = {}
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        df = df.dropna(how='all')
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])
            df = df.sort_values("Date")
            # Remove rows where ALL data columns are NaN (future placeholder rows)
            # Exclude metadata columns that always have values (Year, Month, etc.)
            meta_cols = {"Year", "Month", "Quarter", "YearMonth", "MonthName", "Note"}
            numeric_cols = [c for c in df.select_dtypes(include='number').columns
                           if c not in meta_cols]
            if numeric_cols:
                df = df.dropna(subset=numeric_cols, how='all')
        data[sheet] = df

    # Overlay any data synced from the Open Data Portal. A source that failed
    # validation is not in the cache, so the workbook keeps serving that sheet.
    return data_sources.apply_live_data(data)


try:
    DATA = load_all_data(_get_file_mtime(), data_sources.live_signature())
except Exception as e:
    st.error(f"خطأ في قراءة الملف: {e}")
    st.stop()

LIVE_MANIFEST = data_sources.read_manifest()


def run_sync(only=None):
    """Refresh from the portal, then drop the cache so the new data is picked up."""
    base = {s: df for s, df in DATA.items()}
    manifest = data_sources.sync_all(base_sheets=base, only=only)
    st.cache_data.clear()
    return manifest


# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────
CHART_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Tajawal", size=12, color="#374151"),
    margin=dict(l=40, r=20, t=50, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
)

COLORS = {
    "primary": "#1B3A5C",
    "secondary": "#2C5F8A",
    "accent": "#3B82F6",
    "success": "#059669",
    "danger": "#dc2626",
    "warning": "#d97706",
    "gray": "#6b7280",
    "light": "#f3f4f6",
    "palette": ["#1B3A5C", "#2C5F8A", "#3B82F6", "#059669", "#d97706", "#dc2626", "#8b5cf6", "#ec4899"],
}


def make_card(label, value, delta=None, delta_good_up=True, fmt="{:,.0f}"):
    val_str = fmt.format(value) if not pd.isna(value) else "—"
    delta_html = ""
    if delta is not None and not pd.isna(delta):
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "●"
        if delta_good_up:
            css = "up" if delta > 0 else "down" if delta < 0 else "neutral"
        else:
            css = "down" if delta > 0 else "up" if delta < 0 else "neutral"
        delta_html = f'<div class="kpi-delta {css}">{arrow} {abs(delta):.1f}%</div>'
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{val_str}</div>
        {delta_html}
    </div>"""


def calc_change(series, periods=1):
    clean = series.dropna()
    if len(clean) < periods + 1:
        return None
    curr = clean.iloc[-1]
    prev = clean.iloc[-(periods + 1)]
    if prev == 0:
        return None
    return ((curr - prev) / prev) * 100


def aggregate_data(df, freq, date_col="Date", value_cols=None, method="sum"):
    """Aggregate data by frequency: M=monthly, Q=quarterly, Y=yearly.
    method: 'sum' for flow data (mortgages), 'last' for stock data (loans), 'mean' for indices (CPI).
    """
    if value_cols is None:
        value_cols = [c for c in df.columns if c != date_col and df[c].dtype in ['float64', 'int64', 'float32', 'int32']]
    df = df.copy()
    df = df.set_index(date_col)

    # Detect source frequency
    dates = df.index.dropna().sort_values()
    if len(dates) < 2:
        return df[value_cols].reset_index()
    median_gap = (dates[1:] - dates[:-1]).median().days

    freq_code = {"M": "ME", "Q": "QE", "Y": "YE"}.get(freq, "ME")

    # Don't aggregate if target freq is finer than source
    # e.g. source is quarterly (90d), target is monthly → just return as-is
    target_days = {"M": 30, "Q": 90, "Y": 365}.get(freq, 30)
    if target_days < median_gap * 0.8:
        return df[value_cols].dropna(how="all").reset_index()

    agg_func = {"sum": "sum", "last": "last", "mean": "mean"}.get(method, "sum")
    resampled = df[value_cols].resample(freq_code)
    result = resampled.agg(agg_func)

    if agg_func == "sum":
        # A trailing period that is still filling up (e.g. one month of a quarter)
        # sums to a fraction of a full period and reads as a collapse. Drop it —
        # comparing a partial period against complete ones is not meaningful.
        expected = max(1, round(target_days / median_gap)) if median_gap else 1
        if expected > 1:
            counts = resampled.count().max(axis=1)
            keep = counts >= expected
            # Only trim from the tail; gaps inside the series stay as they are.
            if len(keep) and not keep.iloc[-1]:
                result = result.iloc[:-1]

    result = result.dropna(how="all").reset_index()
    # Remove rows that are all zeros (empty periods summed to 0)
    numeric = result[value_cols]
    result = result[~((numeric == 0) | numeric.isna()).all(axis=1)]
    return result


def add_change_columns(df, date_col="Date", value_cols=None, change_type="yoy"):
    """Add percentage change columns. change_type: 'yoy' (year-over-year), 'qoq' (quarter-over-quarter), 'mom' (month-over-month)."""
    if value_cols is None:
        value_cols = [c for c in df.columns if c != date_col and df[c].dtype in ['float64', 'int64', 'float32', 'int32']]
    df = df.copy()
    periods_map = {"yoy": 4, "qoq": 1, "mom": 1}
    periods = periods_map.get(change_type, 1)
    for col in value_cols:
        df[f"تغير {col} %"] = df[col].pct_change(periods=periods) * 100
    return df


def _clean_for_plot(df, x, y_cols):
    """Remove rows where all y columns are NaN and format dates for cleaner charts."""
    if isinstance(y_cols, str):
        y_cols = [y_cols]
    result = df.copy()
    mask = result[y_cols].notna().any(axis=1)
    result = result[mask]
    # Format dates as readable strings
    if x in result.columns and pd.api.types.is_datetime64_any_dtype(result[x]):
        result[x] = result[x].dt.strftime("%Y-%m")
    return result


def plot_line(df, x, y, title, color=None, fill=True, height=380):
    if color is None:
        color = COLORS["primary"]
    df = _clean_for_plot(df, x, [y])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y], mode="lines+markers", name=y,
        line=dict(color=color, width=2.5), marker=dict(size=5),
        fill="tozeroy" if fill else None,
        fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.06)" if fill else None,
        connectgaps=False,
    ))
    fig.update_layout(title=title, height=height, **CHART_LAYOUT)
    fig.update_xaxes(type="category", tickangle=-45, nticks=20)
    return fig


def plot_multi_line(df, x, y_cols, title, colors=None, height=400):
    df = _clean_for_plot(df, x, y_cols)
    fig = go.Figure()
    if colors is None:
        colors = COLORS["palette"]
    for i, col in enumerate(y_cols):
        fig.add_trace(go.Scatter(
            x=df[x], y=df[col], mode="lines+markers", name=col,
            line=dict(color=colors[i % len(colors)], width=2.5), marker=dict(size=4),
            connectgaps=False,
        ))
    fig.update_layout(title=title, height=height, **CHART_LAYOUT)
    fig.update_xaxes(type="category", tickangle=-45, nticks=20)
    return fig


def plot_bar_comparison(df, x, y_cols, title, colors=None, barmode="group", height=400):
    df = _clean_for_plot(df, x, y_cols)
    fig = go.Figure()
    if colors is None:
        colors = COLORS["palette"]
    for i, col in enumerate(y_cols):
        fig.add_trace(go.Bar(
            x=df[x], y=df[col], name=col,
            marker_color=colors[i % len(colors)],
        ))
    fig.update_layout(title=title, barmode=barmode, height=height, **CHART_LAYOUT)
    fig.update_xaxes(type="category", tickangle=-45, nticks=20)
    return fig


def plot_pie(labels, values, title, height=380):
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.45,
        marker_colors=COLORS["palette"],
        textinfo="label+percent",
        textfont=dict(size=11),
    )])
    fig.update_layout(title=title, height=height, **CHART_LAYOUT, showlegend=False)
    return fig


def render_html_table(df, max_rows=20):
    """Render a pandas DataFrame as a formal HTML table."""
    df_display = df.head(max_rows).copy()
    rows_html = ""
    for _, row in df_display.iterrows():
        cells = ""
        for col in df_display.columns:
            val = row[col]
            if isinstance(val, (int, float, np.integer, np.floating)) and not pd.isna(val):
                if abs(val) >= 1000:
                    cell_val = f"{val:,.0f}"
                elif abs(val) < 10:
                    cell_val = f"{val:.1f}"
                else:
                    cell_val = f"{val:,.0f}"
                # Color change columns
                if "تغير" in str(col) or "%" in str(col):
                    if val > 0:
                        cell_val = f'<span style="color:#059669;">▲ {abs(val):.1f}%</span>'
                    elif val < 0:
                        cell_val = f'<span style="color:#dc2626;">▼ {abs(val):.1f}%</span>'
                    else:
                        cell_val = f'<span style="color:#d97706;">● 0.0%</span>'
            elif isinstance(val, pd.Timestamp):
                cell_val = val.strftime("%Y-%m")
            elif pd.isna(val):
                cell_val = "—"
            else:
                cell_val = str(val)
            cells += f"<td>{cell_val}</td>"
        rows_html += f"<tr>{cells}</tr>"

    headers = "".join(f"<th>{col}</th>" for col in df_display.columns)
    return f"""
    <div style="overflow-x:auto;">
        <table class="styled-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>"""


def generate_analysis(df, value_cols, date_col="Date", title=""):
    """Generate automatic analytical commentary for a dataset."""
    if df.empty or not value_cols:
        return ""

    lines = []
    for col in value_cols[:4]:
        s = df[col].dropna()
        if len(s) < 2:
            continue
        last_val = s.iloc[-1]
        prev_val = s.iloc[-2]
        last_date = df[date_col].iloc[-1]
        if isinstance(last_date, pd.Timestamp):
            last_date = last_date.strftime("%Y-%m")

        if prev_val != 0:
            change_pct = ((last_val - prev_val) / abs(prev_val)) * 100
            direction = "ارتفاع" if change_pct > 0 else "انخفاض" if change_pct < 0 else "استقرار"
            lines.append(
                f"- سجّل مؤشر **{col}** قيمة **{last_val:,.0f}** في الفترة ({last_date})، "
                f"بنسبة {direction} بلغت **{abs(change_pct):.1f}%** مقارنة بالفترة السابقة."
            )

        # Trend (last 4 periods)
        if len(s) >= 4:
            recent = s.iloc[-4:]
            diffs = recent.diff().dropna()
            if (diffs > 0).all():
                lines.append(f"  - يُظهر **{col}** اتجاهاً تصاعدياً مستمراً خلال آخر 4 فترات.")
            elif (diffs < 0).all():
                lines.append(f"  - يُظهر **{col}** اتجاهاً تنازلياً مستمراً خلال آخر 4 فترات.")

    if not lines:
        return ""

    analysis_html = "<br>".join(lines)
    return f"""
    <div style="background:#f0f7ff;border:1px solid #bfdbfe;border-radius:10px;padding:18px 22px;margin:16px 0;font-size:0.88rem;line-height:1.8;color:#1e3a5f;">
        <div style="font-weight:700;font-size:0.95rem;margin-bottom:8px;color:#1B3A5C;">قراءة تحليلية{(' - ' + title) if title else ''}</div>
        {analysis_html}
    </div>"""


def get_last_date(df):
    if "Date" in df.columns:
        last = df["Date"].max()
        if pd.notna(last):
            return last.strftime("%Y-%m-%d")
    return "—"


# ──────────────────────────────────────────────
# Navigation
# ──────────────────────────────────────────────
PAGES = {
    "الرئيسية": "home",
    "التمويل العقاري": "finance",
    "الناتج المحلي": "gdp",
    "الأسعار والتضخم": "cpi",
    "مؤشر الأسعار العقارية": "realestate",
    "تكاليف البناء": "cci",
    "سوق العمل": "labor",
    "الاقتصاد الكلي": "macro",
    "ساما — القطاع المصرفي": "sama",
    "مصادر البيانات": "sources",
}

with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:16px 0 8px 0;">
        <div style="font-size:1.2rem;font-weight:700;color:#1B3A5C;">لوحة المؤشرات</div>
        <div style="font-size:0.75rem;color:#6b7280;">الاقتصادية والاجتماعية</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio("التنقل", list(PAGES.keys()), label_visibility="collapsed")
    st.markdown("---")
    st.markdown(f"<div style='text-align:center;font-size:0.7rem;color:#9ca3af;'>آخر تحديث للبيانات<br>{get_last_date(DATA.get('GDP_Data', pd.DataFrame()))}</div>", unsafe_allow_html=True)

    _live_sources = LIVE_MANIFEST.get("sources") or {}
    _live_ok = sum(1 for e in _live_sources.values() if e.get("status") == "ok")
    _live_bad = len(_live_sources) - _live_ok
    if _live_sources:
        _sync_at = (LIVE_MANIFEST.get("last_sync") or "")[:16].replace("T", " ")
        _badge = f"🟢 {_live_ok} مصدر حي" + (f" · ⚠️ {_live_bad}" if _live_bad else "")
        st.markdown(
            f"<div style='text-align:center;font-size:0.7rem;color:#6b7280;margin-top:6px;'>"
            f"{_badge}<br>آخر مزامنة: {_sync_at or '—'}</div>",
            unsafe_allow_html=True)

    if st.button("تحديث البيانات", use_container_width=True):
        if _live_sources or any(s.enabled for s in data_sources.load_config()):
            with st.spinner("جارٍ جلب البيانات من بوابة البيانات المفتوحة..."):
                run_sync()
        else:
            st.cache_data.clear()
        st.rerun()

current_page = PAGES[page]


# ══════════════════════════════════════════════
# HOME PAGE
# ══════════════════════════════════════════════
if current_page == "home":
    st.markdown(f"""
    <div class="main-header">
        <div>
            <h1>لوحة المؤشرات الاقتصادية والاجتماعية</h1>
            <div class="subtitle">ملخص تنفيذي لأهم المؤشرات الاقتصادية والاجتماعية</div>
        </div>
        <div class="date-badge">تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d')}</div>
    </div>
    """, unsafe_allow_html=True)

    # Row 1: Main KPIs
    gdp = DATA.get("GDP_Data", pd.DataFrame())
    pop = DATA.get("Population", pd.DataFrame())
    cpi_df = DATA.get("cpi", pd.DataFrame())
    rel = DATA.get("Real Estate Loans by Banks", pd.DataFrame())

    c1, c2, c3, c4 = st.columns(4)
    if "الناتج المحلي الاجمالي" in gdp.columns:
        s = gdp["الناتج المحلي الاجمالي"].dropna()
        with c1:
            st.markdown(make_card("الناتج المحلي الإجمالي (مليون ر.س)", s.iloc[-1], calc_change(s, 4)), unsafe_allow_html=True)

    if "الاجمالي" in pop.columns:
        s = pop["الاجمالي"].dropna()
        with c2:
            st.markdown(make_card("عدد السكان", s.iloc[-1], calc_change(s, 1)), unsafe_allow_html=True)

    if "الرقم القياسي العام" in cpi_df.columns:
        s = cpi_df["الرقم القياسي العام"].dropna()
        with c3:
            st.markdown(make_card("مؤشر أسعار المستهلك", s.iloc[-1], calc_change(s, 12), delta_good_up=False, fmt="{:.1f}"), unsafe_allow_html=True)

    if "الاجمالي" in rel.columns:
        s = rel["الاجمالي"].dropna()
        with c4:
            st.markdown(make_card("القروض العقارية (مليون)", s.iloc[-1], calc_change(s, 4)), unsafe_allow_html=True)

    # Row 2: Secondary KPIs
    fdi = DATA.get("FDI", pd.DataFrame())
    cc = DATA.get("CONSUMER  AND CREDIT CARD", pd.DataFrame())
    hh = DATA.get("households", pd.DataFrame())
    si = DATA.get("Active Social Insurance Subscri", pd.DataFrame())

    c5, c6, c7, c8 = st.columns(4)
    if "التدفقات الداخلة" in fdi.columns:
        s = fdi["التدفقات الداخلة"].dropna()
        if len(s) > 0:
            with c5:
                st.markdown(make_card("الاستثمار الأجنبي الداخل", s.iloc[-1], calc_change(s, 4)), unsafe_allow_html=True)

    cc_col = "القروض الاستهلاكية والبطاقات الائتمانية"
    if cc_col in cc.columns:
        s = cc[cc_col].dropna()
        if len(s) > 0:
            with c6:
                st.markdown(make_card("القروض الاستهلاكية", s.iloc[-1], calc_change(s, 4)), unsafe_allow_html=True)

    if "الاجمالي" in hh.columns:
        s = hh["الاجمالي"].dropna()
        if len(s) > 0:
            with c7:
                st.markdown(make_card("عدد الأسر", s.iloc[-1], calc_change(s, 1)), unsafe_allow_html=True)

    if "الاجمالي" in si.columns:
        s = si["الاجمالي"].dropna()
        if len(s) > 0:
            with c8:
                st.markdown(make_card("مشتركي التأمينات", s.iloc[-1], calc_change(s, 4)), unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Overview Charts
    col1, col2 = st.columns(2)
    with col1:
        if "الناتج المحلي الاجمالي" in gdp.columns:
            st.plotly_chart(plot_line(gdp, "Date", "الناتج المحلي الاجمالي", "الناتج المحلي الإجمالي"), use_container_width=True)
    with col2:
        if "الرقم القياسي العام" in cpi_df.columns:
            st.plotly_chart(plot_line(cpi_df, "Date", "الرقم القياسي العام", "مؤشر أسعار المستهلك", COLORS["warning"]), use_container_width=True)


# ══════════════════════════════════════════════
# REAL ESTATE FINANCE PAGE (Detailed)
# ══════════════════════════════════════════════
elif current_page == "finance":
    st.markdown('<div class="page-title">التمويل العقاري</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">تحليل تفصيلي للتمويل العقاري من المصارف وشركات التمويل</div>', unsafe_allow_html=True)

    # Load data
    loans_banks = DATA.get("Real Estate Loans by Banks", pd.DataFrame()).copy()
    mort_banks = DATA.get("Residential New Mortgages Banks", pd.DataFrame()).copy()
    mort_companies = DATA.get("Residential New MortgaCompanies", pd.DataFrame()).copy()

    # ── Filter Bar ──
    st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
    fc1, fc2, fc3, fc4 = st.columns(4)

    with fc1:
        source_filter = st.selectbox("المصدر", ["الكل", "المصارف", "شركات التمويل"], key="fin_source")
    with fc2:
        type_filter = st.selectbox("النوع", ["الإجمالي", "الأفراد", "الشركات"], key="fin_type")
    with fc3:
        period_filter = st.selectbox("عرض البيانات", ["شهري", "ربعي", "سنوي"], key="fin_period")
    with fc4:
        compare_filter = st.selectbox("المقارنة", ["سنوي (YoY)", "ربعي (QoQ)"], key="fin_compare")

    st.markdown('</div>', unsafe_allow_html=True)

    freq_map = {"شهري": "M", "ربعي": "Q", "سنوي": "Y"}
    freq = freq_map[period_filter]

    change_type = "yoy" if "سنوي" in compare_filter else "qoq"

    # ── Section 1: Real Estate Loans (Banks) - Individuals/Companies ──
    if not loans_banks.empty and source_filter in ["الكل", "المصارف"]:
        st.markdown('<div class="section-title">القروض العقارية من المصارف</div>', unsafe_allow_html=True)

        loan_cols = ["الاجمالي", "الافراد", "الشركات"]
        loan_cols = [c for c in loan_cols if c in loans_banks.columns]

        # Type filter
        if type_filter == "الأفراد":
            display_cols = [c for c in loan_cols if c in ["الافراد"]]
        elif type_filter == "الشركات":
            display_cols = [c for c in loan_cols if c in ["الشركات"]]
        else:
            display_cols = loan_cols

        if display_cols:
            # Aggregate
            agg_loans = aggregate_data(loans_banks, freq, value_cols=display_cols, method="last")

            # KPI Cards
            cols = st.columns(len(display_cols))
            for i, col_name in enumerate(display_cols):
                s = agg_loans[col_name].dropna()
                if len(s) > 0:
                    periods = 12 if change_type == "yoy" else 1
                    if freq == "Q":
                        periods = 4 if change_type == "yoy" else 1
                    elif freq == "Y":
                        periods = 1
                    with cols[i]:
                        st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, min(periods, len(s)-1))), unsafe_allow_html=True)

            # Charts
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(plot_multi_line(agg_loans, "Date", display_cols, "القروض العقارية عبر الزمن"), use_container_width=True)
            with col2:
                if len(display_cols) > 1:
                    last_row = agg_loans.iloc[-1]
                    pie_vals = [last_row[c] for c in display_cols if c != "الاجمالي" and not pd.isna(last_row.get(c, np.nan))]
                    pie_labels = [c for c in display_cols if c != "الاجمالي" and not pd.isna(last_row.get(c, np.nan))]
                    if pie_vals:
                        st.plotly_chart(plot_pie(pie_labels, pie_vals, "توزيع القروض - آخر فترة"), use_container_width=True)
                else:
                    # Bar chart for single column over time
                    st.plotly_chart(plot_bar_comparison(agg_loans.tail(12), "Date", display_cols, "المقارنة الزمنية"), use_container_width=True)

            # Analysis
            st.markdown(generate_analysis(agg_loans, display_cols, title="القروض العقارية"), unsafe_allow_html=True)

            # Detailed Table
            st.markdown('<div class="section-title">جدول تفصيلي</div>', unsafe_allow_html=True)
            table_df = add_change_columns(agg_loans, value_cols=display_cols, change_type=change_type)
            display_table_cols = ["Date"] + display_cols + [f"تغير {c} %" for c in display_cols if f"تغير {c} %" in table_df.columns]
            table_df = table_df[display_table_cols].tail(20).sort_values("Date", ascending=False)
            st.markdown(render_html_table(table_df), unsafe_allow_html=True)

    # ── Section 2: New Mortgages - Banks ──
    if not mort_banks.empty and source_filter in ["الكل", "المصارف"]:
        st.markdown('<div class="section-title">الرهون العقارية الجديدة - المصارف</div>', unsafe_allow_html=True)

        m_cols = ["Total", "Apartments", "Houses ", "Land"]
        m_cols = [c for c in m_cols if c in mort_banks.columns]

        if m_cols:
            agg_mort = aggregate_data(mort_banks, freq, value_cols=m_cols, method="sum")

            cols = st.columns(len(m_cols))
            labels_map = {"Total": "الإجمالي", "Apartments": "شقق", "Houses ": "فلل", "Land": "أراضي"}
            for i, col_name in enumerate(m_cols):
                s = agg_mort[col_name].dropna()
                if len(s) > 0:
                    periods = min(4 if freq == "Q" else 12 if freq == "M" else 1, len(s) - 1)
                    if periods > 0:
                        with cols[i]:
                            st.markdown(make_card(labels_map.get(col_name, col_name), s.iloc[-1], calc_change(s, periods)), unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                detail_cols = [c for c in m_cols if c != "Total"]
                if detail_cols:
                    st.plotly_chart(plot_multi_line(agg_mort, "Date", detail_cols, "الرهون حسب النوع - المصارف"), use_container_width=True)
            with col2:
                if "Total" in agg_mort.columns:
                    st.plotly_chart(plot_bar_comparison(agg_mort.tail(12), "Date", ["Total"], "إجمالي الرهون - المصارف"), use_container_width=True)

            # Table
            table_df = add_change_columns(agg_mort, value_cols=m_cols, change_type=change_type)
            display_table_cols = ["Date"] + m_cols + [f"تغير {c} %" for c in m_cols if f"تغير {c} %" in table_df.columns]
            table_df = table_df[display_table_cols].tail(16).sort_values("Date", ascending=False)
            st.markdown(render_html_table(table_df), unsafe_allow_html=True)

    # ── Section 3: New Mortgages - Finance Companies ──
    if not mort_companies.empty and source_filter in ["الكل", "شركات التمويل"]:
        st.markdown('<div class="section-title">الرهون العقارية الجديدة - شركات التمويل</div>', unsafe_allow_html=True)

        m_cols = ["Total", "Apartments", "Houses ", "Land"]
        m_cols = [c for c in m_cols if c in mort_companies.columns]

        if m_cols:
            agg_mort_c = aggregate_data(mort_companies, freq, value_cols=m_cols, method="sum")

            cols = st.columns(len(m_cols))
            labels_map = {"Total": "الإجمالي", "Apartments": "شقق", "Houses ": "فلل", "Land": "أراضي"}
            for i, col_name in enumerate(m_cols):
                s = agg_mort_c[col_name].dropna()
                if len(s) > 0:
                    periods = min(4 if freq == "Q" else 12 if freq == "M" else 1, len(s) - 1)
                    if periods > 0:
                        with cols[i]:
                            st.markdown(make_card(labels_map.get(col_name, col_name), s.iloc[-1], calc_change(s, periods)), unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                detail_cols = [c for c in m_cols if c != "Total"]
                if detail_cols:
                    st.plotly_chart(plot_multi_line(agg_mort_c, "Date", detail_cols, "الرهون حسب النوع - شركات التمويل"), use_container_width=True)
            with col2:
                if "Total" in agg_mort_c.columns:
                    st.plotly_chart(plot_bar_comparison(agg_mort_c.tail(12), "Date", ["Total"], "إجمالي الرهون - شركات التمويل"), use_container_width=True)

            table_df = add_change_columns(agg_mort_c, value_cols=m_cols, change_type=change_type)
            display_table_cols = ["Date"] + m_cols + [f"تغير {c} %" for c in m_cols if f"تغير {c} %" in table_df.columns]
            table_df = table_df[display_table_cols].tail(16).sort_values("Date", ascending=False)
            st.markdown(render_html_table(table_df), unsafe_allow_html=True)

    # ── Section 4: Combined Comparison (Banks vs Companies) ──
    if source_filter == "الكل" and not mort_banks.empty and not mort_companies.empty:
        st.markdown('<div class="section-title">مقارنة المصارف وشركات التمويل</div>', unsafe_allow_html=True)

        if "Total" in mort_banks.columns and "Total" in mort_companies.columns:
            banks_agg = aggregate_data(mort_banks, freq, value_cols=["Total"], method="sum")
            comp_agg = aggregate_data(mort_companies, freq, value_cols=["Total"], method="sum")

            merged = pd.merge(banks_agg, comp_agg, on="Date", how="outer", suffixes=("_banks", "_companies"))
            merged = merged.rename(columns={"Total_banks": "المصارف", "Total_companies": "شركات التمويل"})
            merged = merged.sort_values("Date").dropna(subset=["المصارف", "شركات التمويل"], how="all")

            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(plot_multi_line(merged, "Date", ["المصارف", "شركات التمويل"], "مقارنة إجمالي الرهون"), use_container_width=True)
            with col2:
                last = merged.dropna().iloc[-1] if len(merged.dropna()) > 0 else None
                if last is not None:
                    st.plotly_chart(plot_pie(
                        ["المصارف", "شركات التمويل"],
                        [last["المصارف"], last["شركات التمويل"]],
                        "حصة السوق - آخر فترة"
                    ), use_container_width=True)


# ══════════════════════════════════════════════
# GDP PAGE
# ══════════════════════════════════════════════
elif current_page == "gdp":
    st.markdown('<div class="page-title">الناتج المحلي الإجمالي</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">تحليل مكونات الناتج المحلي والأنشطة الاقتصادية</div>', unsafe_allow_html=True)

    gdp = DATA.get("GDP_Data", pd.DataFrame()).copy()
    main_cols = ["الناتج المحلي الاجمالي", "القيمة المضافة الاجمالية", "الانشطة النفطية",
                 "الانشطة الغير نفطية", "الانشطة الحكومية", "الانشطة العقارية", "التشييد"]
    main_cols = [c for c in main_cols if c in gdp.columns]

    # Filters
    fc1, fc2 = st.columns(2)
    with fc1:
        gdp_period = st.selectbox("عرض البيانات", ["ربعي", "سنوي"], key="gdp_period")
    with fc2:
        gdp_compare = st.selectbox("المقارنة", ["سنوي (YoY)", "ربعي (QoQ)"], key="gdp_compare")

    freq = "Q" if gdp_period == "ربعي" else "Y"
    change_type = "yoy" if "سنوي" in gdp_compare else "qoq"
    agg_gdp = aggregate_data(gdp, freq, value_cols=main_cols, method="last")

    # KPI Cards Row 1
    if main_cols:
        cols = st.columns(min(4, len(main_cols)))
        for i, col_name in enumerate(main_cols[:4]):
            s = agg_gdp[col_name].dropna()
            if len(s) > 0:
                periods = min(4 if change_type == "yoy" and freq == "Q" else 1, len(s) - 1)
                with cols[i]:
                    st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, max(periods, 1))), unsafe_allow_html=True)

    if len(main_cols) > 4:
        cols2 = st.columns(min(4, len(main_cols[4:])))
        for i, col_name in enumerate(main_cols[4:]):
            s = agg_gdp[col_name].dropna()
            if len(s) > 0:
                with cols2[i]:
                    st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, 1)), unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        if "الناتج المحلي الاجمالي" in agg_gdp.columns:
            st.plotly_chart(plot_line(agg_gdp, "Date", "الناتج المحلي الاجمالي", "الناتج المحلي الإجمالي"), use_container_width=True)
    with col2:
        activity_cols = [c for c in ["الانشطة النفطية", "الانشطة الغير نفطية", "الانشطة الحكومية"] if c in agg_gdp.columns]
        if activity_cols:
            st.plotly_chart(plot_multi_line(agg_gdp, "Date", activity_cols, "مقارنة الأنشطة الاقتصادية"), use_container_width=True)

    # Pie chart
    st.markdown('<div class="section-title">توزيع الأنشطة - آخر فترة</div>', unsafe_allow_html=True)
    pie_cols = [c for c in ["الانشطة النفطية", "الانشطة الغير نفطية", "الانشطة الحكومية", "التشييد", "الانشطة العقارية"] if c in agg_gdp.columns]
    if pie_cols and len(agg_gdp) > 0:
        last_row = agg_gdp.iloc[-1]
        pie_vals = [last_row[c] for c in pie_cols if not pd.isna(last_row.get(c, np.nan))]
        pie_labels = [c for c in pie_cols if not pd.isna(last_row.get(c, np.nan))]
        if pie_vals:
            st.plotly_chart(plot_pie(pie_labels, pie_vals, "توزيع الأنشطة الاقتصادية"), use_container_width=True)

    # Analysis
    st.markdown(generate_analysis(agg_gdp, main_cols[:4], title="الناتج المحلي"), unsafe_allow_html=True)

    # Table
    st.markdown('<div class="section-title">جدول تفصيلي</div>', unsafe_allow_html=True)
    table_df = add_change_columns(agg_gdp, value_cols=main_cols[:4], change_type=change_type)
    t_cols = ["Date"] + main_cols[:4] + [f"تغير {c} %" for c in main_cols[:4] if f"تغير {c} %" in table_df.columns]
    table_df = table_df[t_cols].tail(16).sort_values("Date", ascending=False)
    st.markdown(render_html_table(table_df), unsafe_allow_html=True)


# ══════════════════════════════════════════════
# CPI PAGE
# ══════════════════════════════════════════════
elif current_page == "cpi":
    st.markdown('<div class="page-title">مؤشر أسعار المستهلك والتضخم</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">تحليل التضخم والمؤشرات الفرعية للأسعار</div>', unsafe_allow_html=True)

    cpi_df = DATA.get("cpi", pd.DataFrame()).copy()

    # Filters
    fc1, fc2 = st.columns(2)
    with fc1:
        cpi_period = st.selectbox("عرض البيانات", ["شهري", "ربعي", "سنوي"], key="cpi_period")
    with fc2:
        cpi_compare = st.selectbox("المقارنة", ["سنوي (YoY)", "ربعي (QoQ)", "شهري (MoM)"], key="cpi_compare")

    freq = {"شهري": "M", "ربعي": "Q", "سنوي": "Y"}[cpi_period]
    change_map = {"سنوي (YoY)": "yoy", "ربعي (QoQ)": "qoq", "شهري (MoM)": "mom"}
    change_type = change_map[cpi_compare]

    sub_cols = [c for c in cpi_df.columns if c not in ["Date", "الرقم القياسي العام", "Year", "Month", "MonthName", "Quarter", "YearMonth"] and not c.startswith("Unnamed")]

    all_cpi_cols = ["الرقم القياسي العام"] + sub_cols
    all_cpi_cols = [c for c in all_cpi_cols if c in cpi_df.columns]

    agg_cpi = aggregate_data(cpi_df, freq, value_cols=all_cpi_cols, method="mean")

    # Main KPI
    if "الرقم القياسي العام" in agg_cpi.columns:
        s = agg_cpi["الرقم القياسي العام"].dropna()
        if len(s) > 1:
            periods_map_cpi = {"yoy": 12 if freq == "M" else 4 if freq == "Q" else 1, "qoq": 3 if freq == "M" else 1, "mom": 1}
            p = min(periods_map_cpi.get(change_type, 1), len(s) - 1)
            st.markdown(make_card("الرقم القياسي العام لأسعار المستهلك", s.iloc[-1], calc_change(s, p), delta_good_up=False, fmt="{:.1f}"), unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Top/Bottom movers
    if sub_cols:
        sub_data = []
        for col in sub_cols:
            s = agg_cpi[col].dropna()
            if len(s) > 1:
                p = min(periods_map_cpi.get(change_type, 1), len(s) - 1)
                chg = calc_change(s, p)
                if chg is not None:
                    sub_data.append({"المؤشر": col, "القيمة": s.iloc[-1], "التغيير %": chg})

        if sub_data:
            df_sub = pd.DataFrame(sub_data).sort_values("التغيير %", ascending=False)

            st.markdown('<div class="section-title">أعلى وأدنى تغير</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**الأعلى ارتفاعاً**")
                for _, row in df_sub.head(3).iterrows():
                    st.markdown(make_card(row["المؤشر"][:35], row["القيمة"], row["التغيير %"], delta_good_up=False, fmt="{:.1f}"), unsafe_allow_html=True)
            with c2:
                st.markdown("**الأكثر انخفاضاً**")
                for _, row in df_sub.tail(3).iterrows():
                    st.markdown(make_card(row["المؤشر"][:35], row["القيمة"], row["التغيير %"], delta_good_up=False, fmt="{:.1f}"), unsafe_allow_html=True)

    # Chart
    if "الرقم القياسي العام" in agg_cpi.columns:
        st.plotly_chart(plot_line(agg_cpi, "Date", "الرقم القياسي العام", "الرقم القياسي العام عبر الزمن", COLORS["warning"]), use_container_width=True)

    # Compare sub-indices
    st.markdown('<div class="section-title">مقارنة المؤشرات الفرعية</div>', unsafe_allow_html=True)
    selected = st.multiselect("اختر مؤشرات", sub_cols, default=sub_cols[:3] if len(sub_cols) >= 3 else sub_cols)
    if selected:
        st.plotly_chart(plot_multi_line(agg_cpi, "Date", selected, "مقارنة المؤشرات"), use_container_width=True)

    # Analysis
    st.markdown(generate_analysis(agg_cpi, ["الرقم القياسي العام"] + sub_cols[:2], title="الأسعار والتضخم"), unsafe_allow_html=True)

    # Table
    st.markdown('<div class="section-title">جدول تفصيلي</div>', unsafe_allow_html=True)
    table_cols = ["الرقم القياسي العام"] + (selected if selected else sub_cols[:3])
    table_df = add_change_columns(agg_cpi, value_cols=table_cols, change_type=change_type)
    t_cols = ["Date"] + table_cols + [f"تغير {c} %" for c in table_cols if f"تغير {c} %" in table_df.columns]
    table_df = table_df[t_cols].tail(16).sort_values("Date", ascending=False)
    st.markdown(render_html_table(table_df), unsafe_allow_html=True)


# ══════════════════════════════════════════════
# REAL ESTATE PRICE INDEX PAGE
# ══════════════════════════════════════════════
elif current_page == "realestate":
    st.markdown('<div class="page-title">مؤشر الأسعار العقارية</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">تحليل حركة الأسعار العقارية حسب النوع</div>', unsafe_allow_html=True)

    rei = DATA.get("Real Estate Price Index", pd.DataFrame()).copy()
    val_cols = [c for c in rei.columns if c != "Date" and not c.startswith("Unnamed")]

    fc1, fc2 = st.columns(2)
    with fc1:
        rei_period = st.selectbox("عرض البيانات", ["ربعي", "سنوي"], key="rei_period")
    with fc2:
        rei_compare = st.selectbox("المقارنة", ["سنوي (YoY)", "ربعي (QoQ)"], key="rei_compare")

    freq = "Q" if rei_period == "ربعي" else "Y"
    change_type = "yoy" if "سنوي" in rei_compare else "qoq"
    agg_rei = aggregate_data(rei, freq, value_cols=val_cols, method="mean")

    # Main KPI
    if "الرقم القياسي" in agg_rei.columns:
        s = agg_rei["الرقم القياسي"].dropna()
        if len(s) > 0:
            p = min(4 if change_type == "yoy" and freq == "Q" else 1, len(s) - 1)
            st.markdown(make_card("الرقم القياسي العقاري", s.iloc[-1], calc_change(s, max(p, 1)), fmt="{:.1f}"), unsafe_allow_html=True)

    # Sub-index cards
    display = [c for c in val_cols if c != "الرقم القياسي"]
    if display:
        cols = st.columns(min(4, len(display)))
        for i, col_name in enumerate(display[:4]):
            s = agg_rei[col_name].dropna()
            if len(s) > 0:
                with cols[i]:
                    st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, min(1, len(s)-1)), fmt="{:.1f}"), unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        selected_rei = st.multiselect("اختر مؤشرات", val_cols, default=val_cols[:3] if len(val_cols) >= 3 else val_cols, key="rei_multi")
        if selected_rei:
            st.plotly_chart(plot_multi_line(agg_rei, "Date", selected_rei, "مؤشرات الأسعار العقارية"), use_container_width=True)
    with col2:
        if display:
            st.plotly_chart(plot_bar_comparison(agg_rei.tail(8), "Date", display[:3], "مقارنة حسب النوع"), use_container_width=True)

    # Analysis
    st.markdown(generate_analysis(agg_rei, val_cols[:4], title="الأسعار العقارية"), unsafe_allow_html=True)

    # Table
    st.markdown('<div class="section-title">جدول تفصيلي</div>', unsafe_allow_html=True)
    table_df = add_change_columns(agg_rei, value_cols=val_cols, change_type=change_type)
    t_cols = ["Date"] + val_cols + [f"تغير {c} %" for c in val_cols if f"تغير {c} %" in table_df.columns]
    table_df = table_df[t_cols].tail(16).sort_values("Date", ascending=False)
    st.markdown(render_html_table(table_df), unsafe_allow_html=True)


# ══════════════════════════════════════════════
# CONSTRUCTION COST INDEX PAGE
# ══════════════════════════════════════════════
elif current_page == "cci":
    st.markdown('<div class="page-title">مؤشر تكاليف البناء</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">تحليل مكونات تكاليف البناء والتشييد</div>', unsafe_allow_html=True)

    cci = DATA.get("cci", pd.DataFrame()).copy()

    fc1, fc2 = st.columns(2)
    with fc1:
        cci_period = st.selectbox("عرض البيانات", ["شهري", "ربعي", "سنوي"], key="cci_period")
    with fc2:
        cci_compare = st.selectbox("المقارنة", ["سنوي (YoY)", "شهري (MoM)"], key="cci_compare")

    freq = {"شهري": "M", "ربعي": "Q", "سنوي": "Y"}[cci_period]
    change_type = "yoy" if "سنوي" in cci_compare else "mom"

    value_cols = [c for c in cci.columns if c not in ["Date", "Year", "Month", "MonthName", "Quarter", "YearMonth"]
                  and not c.startswith("Number") and not c.startswith("Unnamed")]

    agg_cci = aggregate_data(cci, freq, value_cols=value_cols, method="mean")

    # Main KPI
    if "General Index" in agg_cci.columns:
        s = agg_cci["General Index"].dropna()
        if len(s) > 0:
            p = min(12 if change_type == "yoy" and freq == "M" else 4 if freq == "Q" else 1, len(s) - 1)
            st.markdown(make_card("المؤشر العام لتكاليف البناء", s.iloc[-1], calc_change(s, max(p, 1)), fmt="{:.1f}"), unsafe_allow_html=True)

    display_cols = [c for c in value_cols if c != "General Index"]
    if display_cols:
        cols = st.columns(min(4, len(display_cols)))
        for i, col_name in enumerate(display_cols[:4]):
            s = agg_cci[col_name].dropna()
            if len(s) > 0:
                with cols[i]:
                    st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, min(1, len(s)-1)), fmt="{:.1f}"), unsafe_allow_html=True)

        if len(display_cols) > 4:
            cols2 = st.columns(min(4, len(display_cols[4:8])))
            for i, col_name in enumerate(display_cols[4:8]):
                s = agg_cci[col_name].dropna()
                if len(s) > 0:
                    with cols2[i]:
                        st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, min(1, len(s)-1)), fmt="{:.1f}"), unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    if "General Index" in agg_cci.columns:
        st.plotly_chart(plot_line(agg_cci, "Date", "General Index", "المؤشر العام لتكاليف البناء", COLORS["warning"]), use_container_width=True)

    selected_cci = st.multiselect("اختر عناصر للمقارنة", display_cols, default=display_cols[:3] if len(display_cols) >= 3 else display_cols, key="cci_multi")
    if selected_cci:
        st.plotly_chart(plot_multi_line(agg_cci, "Date", selected_cci, "مقارنة عناصر التكاليف"), use_container_width=True)

    # Analysis
    cci_analysis_cols = (["General Index"] if "General Index" in value_cols else []) + display_cols[:2]
    st.markdown(generate_analysis(agg_cci, cci_analysis_cols, title="تكاليف البناء"), unsafe_allow_html=True)

    # Table
    st.markdown('<div class="section-title">جدول تفصيلي</div>', unsafe_allow_html=True)
    t_val_cols = (["General Index"] if "General Index" in value_cols else []) + display_cols[:3]
    table_df = add_change_columns(agg_cci, value_cols=t_val_cols, change_type=change_type)
    t_cols = ["Date"] + t_val_cols + [f"تغير {c} %" for c in t_val_cols if f"تغير {c} %" in table_df.columns]
    table_df = table_df[t_cols].tail(16).sort_values("Date", ascending=False)
    st.markdown(render_html_table(table_df), unsafe_allow_html=True)


# ══════════════════════════════════════════════
# LABOR MARKET PAGE
# ══════════════════════════════════════════════
elif current_page == "labor":
    st.markdown('<div class="page-title">سوق العمل</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">تحليل سوق العمل والتأمينات الاجتماعية</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["الموظفون حسب المنطقة", "التأمينات الاجتماعية", "المشتركون حسب النشاط"])

    with tab1:
        emp = DATA.get("Employees - Region", pd.DataFrame()).copy()
        regions = [c for c in emp.columns if c not in ["Date", "Overall"]]

        if "Overall" in emp.columns:
            s = emp["Overall"].dropna()
            if len(s) > 0:
                st.markdown(make_card("إجمالي الموظفين", s.iloc[-1], calc_change(s, min(4, len(s)-1))), unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            if "Overall" in emp.columns:
                st.plotly_chart(plot_line(emp, "Date", "Overall", "إجمالي الموظفين"), use_container_width=True)
        with col2:
            if regions and len(emp) > 0:
                last = emp.iloc[-1]
                region_vals = {r: last[r] for r in regions if not pd.isna(last.get(r, np.nan))}
                if region_vals:
                    sorted_regions = sorted(region_vals.items(), key=lambda x: x[1], reverse=True)
                    fig = go.Figure(data=[go.Bar(
                        y=[r[0] for r in sorted_regions],
                        x=[r[1] for r in sorted_regions],
                        orientation="h", marker_color=COLORS["primary"],
                    )])
                    fig.update_layout(title="الموظفون حسب المنطقة", height=400,
                                      **{k: v for k, v in CHART_LAYOUT.items() if k != "legend"})
                    st.plotly_chart(fig, use_container_width=True)

    with tab2:
        si = DATA.get("Active Social Insurance Subscri", pd.DataFrame()).copy()
        si_cols = [c for c in si.columns if c not in ["Date"]]

        if "الاجمالي" in si.columns:
            s = si["الاجمالي"].dropna()
            if len(s) > 0:
                st.markdown(make_card("إجمالي المشتركين", s.iloc[-1], calc_change(s, min(4, len(s)-1))), unsafe_allow_html=True)

        gender_cols = [c for c in si_cols if "سعودي" in c or "غير" in c]
        if gender_cols:
            cols = st.columns(min(3, len(gender_cols)))
            for i, col_name in enumerate(gender_cols[:6]):
                s = si[col_name].dropna()
                if len(s) > 0:
                    with cols[i % 3]:
                        st.markdown(make_card(col_name, s.iloc[-1], calc_change(s, min(4, len(s)-1))), unsafe_allow_html=True)

        display_si = [c for c in si_cols if c != "الاجمالي"][:4]
        if display_si:
            st.plotly_chart(plot_multi_line(si, "Date", display_si, "المشتركون في التأمينات الاجتماعية"), use_container_width=True)

    with tab3:
        ais = DATA.get("Active Insured Subscribers by A", pd.DataFrame()).copy()
        ais_cols = [c for c in ais.columns if c not in ["Date"] and not c.startswith("Unnamed")]

        if ais_cols:
            selected_ais = st.multiselect("اختر أنشطة", ais_cols, default=ais_cols[:3], key="ais_multi")

            # Dynamic KPI cards based on selection
            if selected_ais:
                card_cols = st.columns(min(4, len(selected_ais)))
                for i, col_name in enumerate(selected_ais[:4]):
                    s = ais[col_name].dropna()
                    if len(s) > 0:
                        with card_cols[i]:
                            st.markdown(make_card(col_name[:30], s.iloc[-1], calc_change(s, min(4, len(s)-1))), unsafe_allow_html=True)

                st.plotly_chart(plot_multi_line(ais, "Date", selected_ais, "المشتركون حسب النشاط"), use_container_width=True)
                st.markdown(generate_analysis(ais, selected_ais, title="المشتركون حسب النشاط"), unsafe_allow_html=True)


# ══════════════════════════════════════════════
# MACRO ECONOMY PAGE
# ══════════════════════════════════════════════
elif current_page == "macro":
    st.markdown('<div class="page-title">الاقتصاد الكلي</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">الاستثمار الأجنبي والقروض والسكان</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["الاستثمار الأجنبي", "القروض الاستهلاكية", "السكان والأسر"])

    with tab1:
        fdi = DATA.get("FDI", pd.DataFrame()).copy()
        fdi_cols = ["الاجمالي ", "التدفقات الداخلة", "التدفقات الخارجة"]
        fdi_cols = [c for c in fdi_cols if c in fdi.columns]

        if fdi_cols:
            cols = st.columns(len(fdi_cols))
            for i, col_name in enumerate(fdi_cols):
                s = fdi[col_name].dropna()
                if len(s) > 0:
                    with cols[i]:
                        st.markdown(make_card(col_name.strip(), s.iloc[-1], calc_change(s, min(4, len(s)-1))), unsafe_allow_html=True)

            st.plotly_chart(plot_multi_line(fdi, "Date", fdi_cols, "الاستثمار الأجنبي المباشر"), use_container_width=True)

            if "التدفقات الداخلة" in fdi.columns and "التدفقات الخارجة" in fdi.columns:
                fig = go.Figure()
                fig.add_trace(go.Bar(x=fdi["Date"], y=fdi["التدفقات الداخلة"], name="التدفقات الداخلة", marker_color=COLORS["success"]))
                fig.add_trace(go.Bar(x=fdi["Date"], y=fdi["التدفقات الخارجة"], name="التدفقات الخارجة", marker_color=COLORS["danger"]))
                fig.update_layout(title="مقارنة التدفقات", barmode="group", height=400, **CHART_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

    with tab2:
        cc = DATA.get("CONSUMER  AND CREDIT CARD", pd.DataFrame()).copy()
        cc_col = "القروض الاستهلاكية والبطاقات الائتمانية"
        if cc_col in cc.columns:
            s = cc[cc_col].dropna()
            if len(s) > 0:
                st.markdown(make_card("القروض الاستهلاكية (مليون ر.س)", s.iloc[-1], calc_change(s, min(4, len(s)-1))), unsafe_allow_html=True)
            st.plotly_chart(plot_line(cc, "Date", cc_col, "القروض الاستهلاكية والبطاقات الائتمانية", COLORS["accent"]), use_container_width=True)

    with tab3:
        for sheet_name, title in [("Population", "السكان"), ("households", "الأسر")]:
            df = DATA.get(sheet_name, pd.DataFrame()).copy()
            if df.empty:
                continue

            st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
            regions = [c for c in df.columns if c not in ["Date", "Note", "الاجمالي"]]

            total = df["الاجمالي"].dropna() if "الاجمالي" in df.columns else pd.Series()
            if len(total) > 0:
                st.markdown(make_card(f"إجمالي {title}", total.iloc[-1], calc_change(total, 1)), unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                if "الاجمالي" in df.columns:
                    st.plotly_chart(plot_line(df, "Date", "الاجمالي", f"إجمالي {title} عبر السنوات"), use_container_width=True)
            with col2:
                if regions and len(df) > 0:
                    last = df.iloc[-1]
                    region_vals = {r: last[r] for r in regions if not pd.isna(last.get(r, np.nan))}
                    if region_vals:
                        sorted_r = sorted(region_vals.items(), key=lambda x: x[1], reverse=True)
                        fig = go.Figure(data=[go.Bar(
                            y=[r[0] for r in sorted_r], x=[r[1] for r in sorted_r],
                            orientation="h", marker_color=COLORS["primary"],
                        )])
                        fig.update_layout(title=f"{title} حسب المنطقة", height=400,
                                          **{k: v for k, v in CHART_LAYOUT.items() if k != "legend"})
                        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════
# SAMA PAGE — banking and credit aggregates
# ══════════════════════════════════════════════
elif current_page == "sama":
    st.markdown('<div class="page-title">ساما — القطاع المصرفي والائتمان</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">القروض العقارية والتمويل السكني '
                'والائتمان الاستهلاكي — البنك المركزي السعودي</div>',
                unsafe_allow_html=True)

    loans = DATA.get("Real Estate Loans by Banks", pd.DataFrame()).copy()
    mort_b = DATA.get("Residential New Mortgages Banks", pd.DataFrame()).copy()
    mort_c = DATA.get("Residential New MortgaCompanies", pd.DataFrame()).copy()
    consumer = DATA.get("CONSUMER  AND CREDIT CARD", pd.DataFrame()).copy()

    st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
    f1, f2 = st.columns(2)
    with f1:
        sama_period = st.selectbox("عرض البيانات", ["شهري", "ربعي", "سنوي"],
                                   index=1, key="sama_period")
    with f2:
        sama_compare = st.selectbox("المقارنة", ["سنوي (YoY)", "الفترة السابقة"],
                                    key="sama_compare")
    st.markdown('</div>', unsafe_allow_html=True)

    freq = {"شهري": "M", "ربعي": "Q", "سنوي": "Y"}[sama_period]
    yoy = "سنوي" in sama_compare
    # Periods per year differ by frequency, so a YoY step is 12/4/1 rows.
    step = ({"M": 12, "Q": 4, "Y": 1}[freq]) if yoy else 1

    def _kpi(series, label, good_up=True):
        s = series.dropna()
        if s.empty:
            return make_card(label, float("nan"))
        return make_card(label, s.iloc[-1], calc_change(s, step), good_up)

    # ── Headline numbers ──
    LOAN_COLS = [c for c in ["الاجمالي", "الافراد", "الشركات"] if c in loans.columns]
    agg_loans = (aggregate_data(loans, freq, value_cols=LOAN_COLS, method="last")
                 if LOAN_COLS else pd.DataFrame())
    CONS_COL = "القروض الاستهلاكية والبطاقات الائتمانية"
    agg_cons = (aggregate_data(consumer, freq, value_cols=[CONS_COL], method="last")
                if CONS_COL in consumer.columns else pd.DataFrame())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(_kpi(agg_loans.get("الاجمالي", pd.Series(dtype=float)),
                         "إجمالي القروض العقارية (مليون ريال)"),
                    unsafe_allow_html=True)
    with k2:
        st.markdown(_kpi(agg_loans.get("الافراد", pd.Series(dtype=float)),
                         "قروض الأفراد (مليون ريال)"), unsafe_allow_html=True)
    with k3:
        st.markdown(_kpi(agg_loans.get("الشركات", pd.Series(dtype=float)),
                         "قروض الشركات (مليون ريال)"), unsafe_allow_html=True)
    with k4:
        st.markdown(_kpi(agg_cons.get(CONS_COL, pd.Series(dtype=float)),
                         "الائتمان الاستهلاكي (مليون ريال)"), unsafe_allow_html=True)

    # ── Real estate loans ──
    if not agg_loans.empty:
        st.markdown('<div class="section-title">القروض العقارية من المصارف</div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(plot_multi_line(agg_loans, "Date", LOAN_COLS,
                                            "تطور القروض العقارية"),
                            use_container_width=True)
        with c2:
            last = agg_loans.dropna(subset=LOAN_COLS, how="all").iloc[-1]
            parts = [c for c in ("الافراد", "الشركات") if c in agg_loans.columns
                     and pd.notna(last.get(c))]
            if parts:
                st.plotly_chart(
                    plot_pie(parts, [last[c] for c in parts],
                             "توزيع القروض العقارية"), use_container_width=True)
        st.markdown(generate_analysis(agg_loans, LOAN_COLS, title="القروض العقارية"),
                    unsafe_allow_html=True)

    # ── New residential mortgages: banks vs finance companies ──
    MORT_COLS = ["Apartments", "Houses ", "Land", "Total"]
    have_b = [c for c in MORT_COLS if c in mort_b.columns]
    have_c = [c for c in MORT_COLS if c in mort_c.columns]
    if have_b or have_c:
        st.markdown('<div class="section-title">التمويل السكني الجديد</div>',
                    unsafe_allow_html=True)

        agg_b = aggregate_data(mort_b, freq, value_cols=have_b) if have_b else pd.DataFrame()
        agg_c = aggregate_data(mort_c, freq, value_cols=have_c) if have_c else pd.DataFrame()

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(_kpi(agg_b.get("Total", pd.Series(dtype=float)),
                             "التمويل عبر المصارف"), unsafe_allow_html=True)
        with m2:
            st.markdown(_kpi(agg_c.get("Total", pd.Series(dtype=float)),
                             "التمويل عبر شركات التمويل"), unsafe_allow_html=True)
        with m3:
            tb = agg_b["Total"].dropna() if "Total" in agg_b.columns else pd.Series(dtype=float)
            tc = agg_c["Total"].dropna() if "Total" in agg_c.columns else pd.Series(dtype=float)
            share = (tb.iloc[-1] / (tb.iloc[-1] + tc.iloc[-1]) * 100
                     if len(tb) and len(tc) and (tb.iloc[-1] + tc.iloc[-1]) else float("nan"))
            st.markdown(make_card("حصة المصارف من التمويل السكني", share,
                                  fmt="{:,.1f}%"), unsafe_allow_html=True)

        cc1, cc2 = st.columns(2)
        with cc1:
            if not agg_b.empty:
                by_type = [c for c in ("Apartments", "Houses ", "Land") if c in agg_b.columns]
                st.plotly_chart(
                    plot_bar_comparison(agg_b.tail(12), "Date", by_type,
                                        "التمويل عبر المصارف حسب نوع العقار",
                                        barmode="stack"), use_container_width=True)
        with cc2:
            if not tb.empty and not tc.empty:
                compare = pd.DataFrame({"Date": agg_b["Date"]})
                compare["المصارف"] = agg_b["Total"].values
                merged_c = agg_c.set_index("Date")["Total"] if "Total" in agg_c.columns else None
                if merged_c is not None:
                    compare["شركات التمويل"] = compare["Date"].map(merged_c)
                    st.plotly_chart(
                        plot_multi_line(compare, "Date", ["المصارف", "شركات التمويل"],
                                        "المصارف مقابل شركات التمويل"),
                        use_container_width=True)

    # ── Consumer credit ──
    if not agg_cons.empty:
        st.markdown('<div class="section-title">الائتمان الاستهلاكي والبطاقات</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(plot_line(agg_cons, "Date", CONS_COL,
                                  "القروض الاستهلاكية والبطاقات الائتمانية"),
                        use_container_width=True)
        st.markdown(generate_analysis(agg_cons, [CONS_COL],
                                      title="الائتمان الاستهلاكي"),
                    unsafe_allow_html=True)

    # ── Detail table ──
    if not agg_loans.empty:
        st.markdown('<div class="section-title">البيانات التفصيلية</div>',
                    unsafe_allow_html=True)
        table = add_change_columns(agg_loans.tail(24), value_cols=LOAN_COLS,
                                   change_type="yoy" if yoy else "qoq")
        st.markdown(render_html_table(table.iloc[::-1], max_rows=12),
                    unsafe_allow_html=True)

    st.markdown(
        "<div style='color:#6b7280;font-size:0.78rem;margin-top:18px;'>"
        "المصدر: البنك المركزي السعودي (ساما). لتحديث هذه الأرقام تلقائياً، اضبط "
        "مصادر ساما في صفحة «مصادر البيانات».</div>", unsafe_allow_html=True)



# ══════════════════════════════════════════════
# DATA SOURCES PAGE
# ══════════════════════════════════════════════
elif current_page == "sources":
    st.markdown("""
    <div class="main-header">
        <h1>مصادر البيانات</h1>
        <p>ربط اللوحة ببوابة البيانات المفتوحة — open.data.gov.sa</p>
    </div>
    """, unsafe_allow_html=True)

    specs = data_sources.load_config()
    manifest = data_sources.read_manifest()
    entries = manifest.get("sources") or {}

    configured = [s for s in specs if s.enabled and s.is_configured]
    ok = sum(1 for e in entries.values() if e.get("status") == "ok")
    problems = sum(1 for e in entries.values() if e.get("status") in ("error", "stale"))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(make_card("مصادر مُعرّفة", len(specs)), unsafe_allow_html=True)
    with c2:
        st.markdown(make_card("مصادر مُفعّلة", len(configured)), unsafe_allow_html=True)
    with c3:
        st.markdown(make_card("محدّثة بنجاح", ok), unsafe_allow_html=True)
    with c4:
        st.markdown(make_card("تحتاج مراجعة", problems, delta_good_up=False),
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("تحديث كل المصادر", use_container_width=True, type="primary"):
            with st.spinner("جارٍ جلب البيانات من البوابة..."):
                run_sync()
            st.rerun()
    with col_b:
        last_sync = (manifest.get("last_sync") or "").replace("T", " ")[:19]
        st.markdown(
            f"<div style='padding-top:8px;color:#6b7280;font-size:0.85rem;'>"
            f"آخر مزامنة: {last_sync or 'لم تتم بعد'}</div>",
            unsafe_allow_html=True)

    if not configured:
        st.info(
            "لم يُفعَّل أي مصدر بعد، واللوحة تعمل حالياً من ملف الإكسل المرفق.\n\n"
            "لربط مصدر بالبوابة، افتح `sources.json` وضع لكل مؤشر إمّا `dataset_id` "
            "(معرّف المجموعة في البوابة) أو `resource_url` (رابط ملف CSV/XLSX مباشر)، "
            "ثم اجعل `enabled` تساوي `true`.\n\n"
            "للعثور على المعرّفات نفّذ محلياً:\n"
            "`python sync_data.py discover \"الناتج المحلي الإجمالي\"`"
        )

    st.markdown("<h3 class='section-title'>حالة المصادر</h3>", unsafe_allow_html=True)

    status_label = {"ok": "✅ محدّث", "stale": "⚠️ نسخة سابقة",
                    "error": "❌ فشل", None: "⚪ غير مُفعّل"}
    rows = []
    for spec in specs:
        entry = entries.get(spec.sheet, {})
        status = entry.get("status") if spec.enabled else None
        if spec.enabled and not entry:
            status = "error"
        rows.append({
            "المؤشر": spec.label or spec.sheet,
            "الورقة": spec.sheet,
            "الجهة": spec.publisher,
            "الحالة": status_label.get(status, "⚪ غير مُفعّل"),
            "عدد الصفوف": f"{entry['rows']:,}" if entry.get("rows") else "—",
            "أحدث فترة": entry.get("latest_date") or "—",
            "آخر تحديث": (entry.get("updated_at") or "—").replace("T", " ")[:16],
        })
    st.markdown(render_html_table(pd.DataFrame(rows), max_rows=len(rows)),
                unsafe_allow_html=True)

    failed = {s: e for s, e in entries.items() if e.get("error")}
    if failed:
        st.markdown("<h3 class='section-title'>تفاصيل الأخطاء</h3>",
                    unsafe_allow_html=True)
        for sheet, entry in failed.items():
            with st.expander(f"{entry.get('label') or sheet}"):
                st.write(entry.get("error"))
                if entry.get("source_url"):
                    st.caption(f"الرابط: {entry['source_url']}")

    if configured:
        st.markdown("<h3 class='section-title'>تحديث مصدر واحد</h3>",
                    unsafe_allow_html=True)
        choice = st.selectbox("اختر المؤشر",
                              [s.sheet for s in configured],
                              format_func=lambda sh: next(
                                  (s.label or s.sheet for s in configured
                                   if s.sheet == sh), sh))
        if st.button("تحديث المصدر المحدد"):
            with st.spinner("جارٍ التحديث..."):
                run_sync(only=choice)
            st.rerun()

    with st.expander("كيف تعمل آلية التحديث؟"):
        st.markdown("""
- **ملف الإكسل** في مجلد `data/` هو الأساس، ويبقى يعمل دائماً حتى لو تعذّر الوصول للبوابة.
- **المصادر المُفعّلة** في `sources.json` تُجلب من البوابة وتُخزَّن في `data/live/`.
- عند العرض تُدمج البيانات الحية فوق الإكسل: `extend` يبقي التاريخ القديم ويضيف/يحدّث الفترات الجديدة، و`replace` يستبدل الورقة بالكامل.
- **التحقق قبل العرض**: أي مصدر لا يحتوي عمود تاريخ أو أعمدة رقمية أو لا تطابق أعمدته الورقة الحالية يُرفض ويُسجَّل هنا، ولا يصل إلى الرسوم.
- **التحديث التلقائي**: مهمة `.github/workflows/sync-data.yml` تعمل يومياً وتحفظ أي بيانات جديدة في المستودع، فتظهر في اللوحة دون تدخل.
        """)



# ──────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────
st.markdown('<div class="report-footer">لوحة المؤشرات الاقتصادية والاجتماعية | البيانات تتحدث تلقائياً من بوابة البيانات المفتوحة وملف Excel المرفق</div>', unsafe_allow_html=True)
