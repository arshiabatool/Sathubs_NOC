"""
================================================================================
 SATHUBS LLC - NOC TERMINAL MONITORING DASHBOARD
================================================================================
A professional, auto-refreshing Network Operations Center dashboard that reads
live data directly from Google Sheets, cleans it, and visualizes terminal
status across multiple satellite networks (HS4, ABS-2A, NSS-12, etc.)

Author : Built for Sathubs LLC
Stack  : Python + Streamlit + Pandas + Plotly
Cost   : 100% free (Streamlit Community Cloud + public Google Sheet CSV export)
================================================================================
"""

import base64
import io
import os
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# =============================================================================
# 0. PAGE CONFIG  (must be the first Streamlit call)
# =============================================================================
st.set_page_config(
    page_title="Sathubs LLC | NOC Dashboard",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# 1. CONFIGURATION  ---- EDIT THIS SECTION FOR YOUR OWN SHEETS -----------------
# =============================================================================
# Your Google Spreadsheet ID (the long string in the sheet URL between /d/ and /edit)
SPREADSHEET_ID = "1GQP3xI9bFU36LM4PpYBxl7fMcqcsoyKM"

# Every tab (gid) inside that spreadsheet that should be pulled into the dashboard.
# key   = a friendly label used only if a "Network" column can't be found in the sheet
# value = the gid number from the sheet URL (...#gid=XXXXXXX)
SHEETS = {
    "HS4 & ABS-2A Sites": "95063111",
    "NSS-12 & AsiaSat 5A Sites": "1394382842",
    # Uncomment and fill in if you have a confirmed 3rd tab in this spreadsheet:
    # "Additional Sites": "194083809",
}

# The closed set of customers that actually exist in your sheets. Any row whose
# Customer Name doesn't match one of these (after loose matching) is treated as
# junk (title rows, note rows, the ESID lookup table at the bottom of the sheet,
# etc.) and is dropped automatically during cleaning. Edit this if you add a
# new customer.
KNOWN_CUSTOMERS = {
    "akc": "AKC",
    "azh": "AZH",
    "ali": "ALI (BGP)",
    "shaheen": "Shaheen Shah (BGP)",
    "starwin": "Starwin",
    "xn": "XN",
    "sbg": "SBG-Hadi",
    "hadi": "SBG-Hadi",
}

# The satellite networks that actually exist. Any value that doesn't match one
# of these is kept as-is under an "Other" bucket rather than silently dropped,
# so new/unexpected networks are still visible on the dashboard for QA.
KNOWN_NETWORKS = {
    "hs4": "HS4", "hs-4": "HS4", "hs 4": "HS4",
    "abs-2a": "ABS-2A", "abs 2a": "ABS-2A", "abs2a": "ABS-2A", "abs-2": "ABS-2A",
    "nss-12": "NSS-12", "nss12": "NSS-12", "nss 12": "NSS-12",
    "asiasat 5a": "AsiaSat 5A", "as-5a": "AsiaSat 5A", "as 5a": "AsiaSat 5A",
    "asiasat5a": "AsiaSat 5A", "as5a": "AsiaSat 5A",
}

# Company branding
COMPANY_NAME = "Sathubs LLC"
DASHBOARD_TITLE = "Sathubs LLC — NOC"
LOGO_FILENAME = "logo.jpg"  # must sit in the SAME GitHub repo folder as app.py

# Auto-refresh interval (seconds) - default value, user can change in sidebar
DEFAULT_REFRESH_SECONDS = 60

# Cache TTL should match refresh interval so new data is actually fetched
CACHE_TTL_SECONDS = DEFAULT_REFRESH_SECONDS

# =============================================================================
# 2. STYLING  — professional dark NOC theme + top header bar
# =============================================================================
CUSTOM_CSS = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent;}

    .block-container {padding-top: 1rem; padding-bottom: 2rem;}

    /* ---- Top header bar ---- */
    .noc-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: linear-gradient(90deg, #0B0F19 0%, #131A29 60%, #0B0F19 100%);
        border: 1px solid #1F2937;
        border-radius: 10px;
        padding: 14px 24px;
        margin-bottom: 18px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.35);
    }
    .noc-header-left {display: flex; align-items: center; gap: 14px;}
    .noc-header-left img {
        height: 46px;
        width: 46px;
        border-radius: 8px;
        object-fit: cover;
        border: 1px solid #2A3444;
        background: #fff;
    }
    .noc-title {
        font-size: 24px;
        font-weight: 800;
        letter-spacing: 0.5px;
        color: #F0F6FC;
        margin: 0;
        line-height: 1.1;
    }
    .noc-subtitle {
        font-size: 12.5px;
        color: #7D8590;
        margin: 0;
        letter-spacing: 0.5px;
    }
    .noc-header-right {text-align: right;}
    .noc-live-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(0, 212, 255, 0.10);
        border: 1px solid rgba(0, 212, 255, 0.35);
        color: #00D4FF;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .noc-live-dot {
        height: 8px; width: 8px; border-radius: 50%;
        background: #00E676;
        box-shadow: 0 0 8px #00E676;
        animation: pulse 1.6s infinite;
    }
    @keyframes pulse {
        0% {opacity: 1;} 50% {opacity: 0.35;} 100% {opacity: 1;}
    }
    .noc-updated {color: #7D8590; font-size: 11.5px; margin-top: 4px;}

    /* ---- KPI cards ---- */
    .kpi-card {
        background: linear-gradient(145deg, #131A29, #0F1523);
        border: 1px solid #1F2937;
        border-left: 4px solid #00D4FF;
        border-radius: 10px;
        padding: 16px 18px;
        height: 100%;
    }
    .kpi-label {
        font-size: 12px;
        color: #8B949E;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 4px;
        font-weight: 600;
    }
    .kpi-value {
        font-size: 30px;
        font-weight: 800;
        color: #F0F6FC;
        line-height: 1.1;
    }
    .kpi-sub {font-size: 11.5px; color: #6E7681; margin-top: 4px;}
    .kpi-green {border-left-color: #00E676;}
    .kpi-red {border-left-color: #FF5252;}
    .kpi-amber {border-left-color: #FFB300;}
    .kpi-blue {border-left-color: #00D4FF;}
    .kpi-purple {border-left-color: #B388FF;}

    section[data-testid="stSidebar"] {
        background: #0F1523;
        border-right: 1px solid #1F2937;
    }

    .section-title {
        font-size: 17px;
        font-weight: 700;
        color: #F0F6FC;
        margin: 6px 0 10px 0;
        padding-left: 10px;
        border-left: 3px solid #00D4FF;
    }

    .alert-box {
        background: rgba(255, 82, 82, 0.08);
        border: 1px solid rgba(255, 82, 82, 0.35);
        border-radius: 8px;
        padding: 10px 14px;
        color: #FFB4B4;
        font-size: 13px;
        margin-bottom: 10px;
    }
    .ok-box {
        background: rgba(0, 230, 118, 0.08);
        border: 1px solid rgba(0, 230, 118, 0.35);
        border-radius: 8px;
        padding: 10px 14px;
        color: #B9F6CA;
        font-size: 13px;
        margin-bottom: 10px;
    }

    div[data-testid="stMetric"] {
        background: #131A29;
        border: 1px solid #1F2937;
        border-radius: 10px;
        padding: 10px 14px;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =============================================================================
# 3. HEADER BAR  (logo top-left + dashboard name + live status)
# =============================================================================
def _get_logo_base64(filename: str):
    """Look for the logo next to app.py (as committed in the GitHub repo)."""
    candidates = [
        filename,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename),
        os.path.join("assets", filename),
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return None


def render_header():
    logo_b64 = _get_logo_base64(LOGO_FILENAME)
    if logo_b64:
        logo_html = f'<img src="data:image/jpeg;base64,{logo_b64}" alt="logo">'
    else:
        # graceful fallback if logo.jpg hasn't been committed yet
        logo_html = (
            '<div style="height:46px;width:46px;border-radius:8px;'
            'background:#00D4FF;color:#0B0F19;display:flex;align-items:center;'
            'justify-content:center;font-weight:800;font-size:18px;">SL</div>'
        )

    now_str = datetime.now().strftime("%A, %d %b %Y — %H:%M:%S")
    st.markdown(
        f"""
        <div class="noc-header">
            <div class="noc-header-left">
                {logo_html}
                <div>
                    <p class="noc-title">{DASHBOARD_TITLE}</p>
                    <p class="noc-subtitle">TERMINAL MONITORING &amp; NETWORK OPERATIONS CENTER</p>
                </div>
            </div>
            <div class="noc-header-right">
                <span class="noc-live-badge"><span class="noc-live-dot"></span> LIVE</span>
                <div class="noc-updated">Last sync: {now_str}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


render_header()

# =============================================================================
# 4. DATA LOADING  — pull each sheet tab as CSV (no API key / no cost)
# =============================================================================
def _csv_export_url(spreadsheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


# Canonical column names we want the final dataframe to have, mapped from the
# many possible header variants that might appear in messy real-world sheets.
COLUMN_ALIASES = {
    "Customer Name": [
        "customer name", "customer", "client", "client name", "cust name",
        "cust", "account name", "party name", "customer/site", "company",
    ],
    "Terminal Name": [
        "terminal name", "terminal", "site name", "site", "location",
        "terminal id", "site id", "terminal/site",
        "new names", "service packages", "remotes",
        "new names service packages remotes",
    ],
    "Modem Number": [
        "modem number", "modem no", "modem no.", "modem sr no", "modem serial",
        "modem s/n", "serial number", "modem sl no", "modem", "sr no", "s/n",
    ],
    "Network": [
        "network", "satellite", "beam", "network name", "sat", "system",
    ],
    "Modem Status": [
        "modem status", "status", "terminal status", "current status", "state",
        "activation status",
    ],
    "Down MIR": [
        "down mir", "d mir", "mir down", "mir(d)", "mir (down)", "downlink mir",
        "dl mir",
    ],
    "Up MIR": [
        "up mir", "u mir", "mir up", "mir(u)", "mir (up)", "uplink mir", "ul mir",
    ],
    "Down CIR": [
        "down cir", "d cir", "cir down", "cir(d)", "cir (down)", "downlink cir",
        "dl cir",
    ],
    "Up CIR": [
        "up cir", "u cir", "cir up", "cir(u)", "cir (up)", "uplink cir", "ul cir",
    ],
}

STATUS_MAP = {
    "a/c": "Activated", "ac": "Activated", "active": "Activated",
    "activated": "Activated", "act": "Activated", "up": "Activated",
    "working": "Activated", "online": "Activated",
    "d/a": "D/A", "da": "D/A", "deactive": "D/A", "deactivated": "D/A",
    "de-active": "D/A", "de active": "D/A", "inactive": "D/A",
    "down": "D/A", "offline": "D/A", "not working": "D/A", "suspended": "D/A",
}


def _normalize(s: str) -> str:
    return (
        str(s).strip().lower()
        .replace("\n", " ").replace("\r", " ")
        .replace("_", " ").replace("-", " ").replace(".", "")
        .replace("  ", " ").strip()
    )


def _find_header_row(raw: pd.DataFrame, max_scan: int = 20) -> int:
    """Scan the first N rows to find which one looks like the real header
    (i.e. contains several of our known column keywords)."""
    all_keywords = set()
    for aliases in COLUMN_ALIASES.values():
        for a in aliases:
            all_keywords.add(_normalize(a))

    best_row, best_score = 0, -1
    for i in range(min(max_scan, len(raw))):
        row_vals = [_normalize(v) for v in raw.iloc[i].tolist() if pd.notna(v)]
        score = sum(1 for v in row_vals if any(kw in v or v in kw for kw in all_keywords))
        if score > best_score:
            best_score, best_row = score, i
    return best_row


def _map_columns(columns) -> dict:
    mapping = {}
    for col in columns:
        norm = _normalize(col)
        matched = None
        for canonical, aliases in COLUMN_ALIASES.items():
            if norm == _normalize(canonical) or any(norm == _normalize(a) for a in aliases):
                matched = canonical
                break
        if not matched:
            for canonical, aliases in COLUMN_ALIASES.items():
                if any(a in norm for a in aliases):
                    matched = canonical
                    break
        mapping[col] = matched if matched else col
    return mapping


def clean_sheet(raw: pd.DataFrame, source_label: str) -> pd.DataFrame:
    """Turn a messy raw sheet (title rows, blank rows, section headers) into a
    clean standardized dataframe."""
    if raw.empty:
        return pd.DataFrame()

    header_row = _find_header_row(raw)
    df = raw.iloc[header_row + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[header_row].tolist()]

    # drop fully empty rows / columns
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    df = df.loc[:, ~df.columns.astype(str).str.contains(r"^Unnamed", na=False)]

    # drop stray section-title rows (rows where almost every cell is empty except one)
    non_null_counts = df.notna().sum(axis=1)
    df = df[non_null_counts >= 2]

    # map to canonical column names
    col_map = _map_columns(df.columns)
    df = df.rename(columns=col_map)

    # collapse duplicate canonical columns (keep first non-null)
    df = df.loc[:, ~df.columns.duplicated()]

    # strip whitespace in text cells
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": pd.NA, "": pd.NA, "None": pd.NA})

    # drop rows with no customer AND no terminal AND no modem info (junk rows)
    key_cols = [c for c in ["Customer Name", "Terminal Name", "Modem Number"] if c in df.columns]
    if key_cols:
        df = df.dropna(subset=key_cols, how="all")

    # normalize status
    def _canon_status(x):
        if pd.isna(x):
            return "Unknown"
        text = str(x).strip()
        if not text or text.lower() == "nan":
            return "Unknown"
        return STATUS_MAP.get(_normalize(text), text)

    if "Modem Status" in df.columns:
        df["Modem Status"] = df["Modem Status"].apply(_canon_status)
    else:
        df["Modem Status"] = "Unknown"

    # numeric bandwidth columns — strip thousands separators ("2,000") BEFORE
    # extracting the number, otherwise "2,000" would be misread as just "2"
    for col in ["Down MIR", "Up MIR", "Down CIR", "Up CIR"]:
        if col in df.columns:
            no_commas = df[col].astype(str).str.replace(",", "", regex=False)
            df[col] = pd.to_numeric(no_commas.str.extract(r"([\d.]+)")[0], errors="coerce")
        else:
            df[col] = pd.NA

    # fill missing Network with the source sheet label
    if "Network" not in df.columns:
        df["Network"] = source_label
    else:
        df["Network"] = df["Network"].fillna(source_label)
        df.loc[df["Network"].astype(str).str.len() == 0, "Network"] = source_label

    for col in ["Customer Name", "Terminal Name", "Modem Number"]:
        if col not in df.columns:
            df[col] = pd.NA

    df["Source Sheet"] = source_label

    # ---- canonicalize Network against the known satellite list ----
    def _canon_network(val):
        if pd.isna(val):
            return "Other"
        norm = _normalize(val)
        for key, canon in KNOWN_NETWORKS.items():
            if norm == key or key in norm:
                return canon
        return str(val).strip() if str(val).strip() else "Other"

    df["Network"] = df["Network"].apply(_canon_network)

    # ---- canonicalize Customer Name against the known customer list ----
    def _canon_customer(val):
        if pd.isna(val):
            return None
        norm = _normalize(val)
        for key, canon in KNOWN_CUSTOMERS.items():
            if key in norm:
                return canon
        return None  # unmatched -> treated as junk (section titles, notes, ESID table, etc.)

    df["Customer Name"] = df["Customer Name"].apply(_canon_customer)

    # ---- final junk filter ----
    # A real terminal row always has a known customer AND a modem number.
    # This single filter removes: the top summary/count blocks, section-title
    # rows ("AKC Terminals"), and any trailing lookup tables (e.g. ESID list)
    # that don't share this sheet's column layout.
    df = df.dropna(subset=["Customer Name", "Modem Number"])
    df = df[df["Modem Number"].astype(str).str.strip() != ""]

    ordered = [
        "Customer Name", "Terminal Name", "Modem Number", "Network",
        "Modem Status", "Down MIR", "Up MIR", "Down CIR", "Up CIR", "Source Sheet",
    ]
    return df[ordered].reset_index(drop=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def load_all_sheets(spreadsheet_id: str, sheets: dict):
    frames = []
    errors = []
    for label, gid in sheets.items():
        url = _csv_export_url(spreadsheet_id, gid)
        try:
            raw = pd.read_csv(url, header=None, dtype=str)
            cleaned = clean_sheet(raw, label)
            if cleaned.empty:
                errors.append(f"⚠️ '{label}' loaded but contained no usable rows after cleaning.")
            else:
                frames.append(cleaned)
        except Exception as e:
            errors.append(f"❌ Could not load '{label}' (gid={gid}): {e}")

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=[
            "Customer Name", "Terminal Name", "Modem Number", "Network",
            "Modem Status", "Down MIR", "Up MIR", "Down CIR", "Up CIR", "Source Sheet",
        ])
    return combined, errors


# =============================================================================
# 5. SIDEBAR — controls & global filters
# =============================================================================
with st.sidebar:
    logo_b64_sidebar = _get_logo_base64(LOGO_FILENAME)
    if logo_b64_sidebar:
        st.markdown(
            f'<img src="data:image/jpeg;base64,{logo_b64_sidebar}" '
            f'style="height:56px;width:56px;border-radius:8px;object-fit:cover;'
            f'margin-bottom:6px;">',
            unsafe_allow_html=True,
        )
    st.markdown(f"### {COMPANY_NAME}")
    st.caption("NOC Control Panel")
    st.divider()

    st.markdown("**⚙️ Auto Refresh**")
    refresh_seconds = st.select_slider(
        "Refresh interval",
        options=[15, 30, 60, 120, 300],
        value=DEFAULT_REFRESH_SECONDS,
        format_func=lambda x: f"{x}s" if x < 60 else f"{x // 60}m",
    )
    auto_refresh_on = st.toggle("Enable auto-refresh", value=True)

    if st.button("🔄 Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.markdown("**🔎 Global Filters**")

# Load data (respect sidebar-chosen refresh interval by keying the cache TTL indirectly)
with st.spinner("Fetching latest data from Google Sheets..."):
    df_all, load_errors = load_all_sheets(SPREADSHEET_ID, SHEETS)

for err in load_errors:
    st.markdown(f'<div class="alert-box">{err}</div>', unsafe_allow_html=True)

if df_all.empty:
    st.error(
        "No data could be loaded from any sheet. Please check that the Google "
        "Sheet is shared as **'Anyone with the link — Viewer'**, and that the "
        "SPREADSHEET_ID / gid values in app.py are correct."
    )
    st.stop()

# ---- sidebar filters (applied globally) ----
with st.sidebar:
    customers = sorted([c for c in df_all["Customer Name"].dropna().unique()])
    networks = sorted([n for n in df_all["Network"].dropna().unique()])
    statuses = sorted([s for s in df_all["Modem Status"].dropna().unique()])

    f_customers = st.multiselect("Customer", customers, default=[])
    f_networks = st.multiselect("Network", networks, default=[])
    f_status = st.multiselect("Status", statuses, default=[])

    st.divider()
    st.caption(f"Rows loaded: **{len(df_all)}**")
    st.caption(f"Networks detected: **{len(networks)}**")
    st.caption(f"Customers detected: **{len(customers)}**")

    csv_buf = io.StringIO()
    df_all.to_csv(csv_buf, index=False)
    st.download_button(
        "⬇️ Export full dataset (CSV)",
        data=csv_buf.getvalue(),
        file_name=f"noc_terminals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

df = df_all.copy()
if f_customers:
    df = df[df["Customer Name"].isin(f_customers)]
if f_networks:
    df = df[df["Network"].isin(f_networks)]
if f_status:
    df = df[df["Modem Status"].isin(f_status)]

# =============================================================================
# 6. AUTO REFRESH  (silent countdown -> full rerun)
# =============================================================================
if auto_refresh_on:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=refresh_seconds * 1000, key="noc_autorefresh")
    except ImportError:
        st.sidebar.warning(
            "Add `streamlit-autorefresh` to requirements.txt to enable "
            "automatic page refresh (falls back to manual refresh for now)."
        )

# =============================================================================
# 7. HELPER — KPI card renderer
# =============================================================================
def kpi_card(col, label, value, sub="", color="kpi-blue"):
    col.markdown(
        f"""
        <div class="kpi-card {color}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


PLOTLY_TEMPLATE = "plotly_dark"
COLOR_SEQ = ["#00D4FF", "#00E676", "#FFB300", "#FF5252", "#B388FF", "#FF8A65", "#26C6DA"]

# =============================================================================
# 8. TABS
# =============================================================================
tab_overview, tab_status, tab_network, tab_customer, tab_details, tab_bw = st.tabs(
    ["📊 Overview", "🟢 Terminal Status", "🛰️ Network Distribution",
     "👥 Customer Summary", "📋 Terminal Details", "📶 Bandwidth Summary"]
)

# ---------------------------------------------------------------- OVERVIEW --
with tab_overview:
    st.markdown('<p class="section-title">Key Performance Indicators</p>', unsafe_allow_html=True)

    total = len(df)
    activated = int((df["Modem Status"] == "Activated").sum())
    da = int((df["Modem Status"] == "D/A").sum())
    other_status = total - activated - da
    activation_rate = (activated / total * 100) if total else 0

    net_counts = df["Network"].value_counts()

    row1 = st.columns(4)
    kpi_card(row1[0], "Total Terminals", f"{total:,}", "All networks combined", "kpi-blue")
    kpi_card(row1[1], "Activated", f"{activated:,}", f"{activation_rate:.1f}% of fleet", "kpi-green")
    kpi_card(row1[2], "D/A (Deactivated)", f"{da:,}", f"{100 - activation_rate:.1f}% of fleet" if total else "—", "kpi-red")
    kpi_card(row1[3], "Networks Detected", f"{df['Network'].nunique()}", "Distinct satellite networks", "kpi-purple")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<p class="section-title">Per-Network Terminal Count</p>', unsafe_allow_html=True)
    net_cols = st.columns(min(len(net_counts), 6) or 1)
    for i, (net, cnt) in enumerate(net_counts.items()):
        kpi_card(net_cols[i % len(net_cols)], str(net), f"{cnt:,}", "terminals", "kpi-amber")

    st.markdown("<br>", unsafe_allow_html=True)

    if total and da / total > 0.5:
        st.markdown(
            f'<div class="alert-box">⚠️ <b>Network Health Alert:</b> {da/total*100:.0f}% of terminals '
            f'are currently D/A. Immediate attention recommended.</div>',
            unsafe_allow_html=True,
        )
    elif total:
        st.markdown(
            f'<div class="ok-box">✅ Network health looks stable — {activation_rate:.0f}% activation rate.</div>',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<p class="section-title">Status Split</p>', unsafe_allow_html=True)
        fig = px.pie(
            names=["Activated", "D/A"] + (["Other"] if other_status else []),
            values=[activated, da] + ([other_status] if other_status else []),
            hole=0.55,
            color_discrete_sequence=["#00E676", "#FF5252", "#FFB300"],
            template=PLOTLY_TEMPLATE,
        )
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown('<p class="section-title">Terminals by Network</p>', unsafe_allow_html=True)
        fig2 = px.bar(
            x=net_counts.index, y=net_counts.values,
            labels={"x": "Network", "y": "Terminals"},
            color=net_counts.index, color_discrete_sequence=COLOR_SEQ,
            template=PLOTLY_TEMPLATE, text=net_counts.values,
        )
        fig2.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=320)
        st.plotly_chart(fig2, use_container_width=True)

# ----------------------------------------------------------- STATUS TAB ----
with tab_status:
    st.markdown('<p class="section-title">Activated vs D/A</p>', unsafe_allow_html=True)
    status_counts = df["Modem Status"].value_counts()

    m1, m2, m3 = st.columns(3)
    m1.metric("Activated", int(status_counts.get("Activated", 0)))
    m2.metric("D/A", int(status_counts.get("D/A", 0)))
    m3.metric("Activation Rate", f"{activation_rate:.1f}%")

    c1, c2 = st.columns(2)
    with c1:
        fig = px.pie(
            names=status_counts.index, values=status_counts.values, hole=0.5,
            color=status_counts.index,
            color_discrete_map={"Activated": "#00E676", "D/A": "#FF5252", "Unknown": "#FFB300"},
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(
            x=status_counts.index, y=status_counts.values,
            color=status_counts.index,
            color_discrete_map={"Activated": "#00E676", "D/A": "#FF5252", "Unknown": "#FFB300"},
            labels={"x": "Status", "y": "Count"}, text=status_counts.values,
            template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(height=340, showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<p class="section-title">Status Breakdown by Network</p>', unsafe_allow_html=True)
    cross = df.groupby(["Network", "Modem Status"]).size().reset_index(name="Count")
    fig = px.bar(
        cross, x="Network", y="Count", color="Modem Status", barmode="group",
        color_discrete_map={"Activated": "#00E676", "D/A": "#FF5252", "Unknown": "#FFB300"},
        template=PLOTLY_TEMPLATE,
    )
    fig.update_layout(height=380, margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------- NETWORK TAB ----
with tab_network:
    st.markdown('<p class="section-title">Network / Satellite Distribution</p>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        fig = px.pie(
            names=net_counts.index, values=net_counts.values, hole=0.4,
            color_discrete_sequence=COLOR_SEQ, template=PLOTLY_TEMPLATE,
        )
        fig.update_traces(textinfo="label+value+percent")
        fig.update_layout(height=380, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.treemap(
            df, path=["Network"], values=None,
            color="Network", color_discrete_sequence=COLOR_SEQ, template=PLOTLY_TEMPLATE,
        )
        fig.update_layout(height=380, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<p class="section-title">Network Health (Activation % per Network)</p>', unsafe_allow_html=True)
    health = (
        df.groupby("Network")["Modem Status"]
        .apply(lambda s: (s == "Activated").mean() * 100)
        .reset_index(name="Activation %")
        .sort_values("Activation %", ascending=False)
    )
    fig = px.bar(
        health, x="Network", y="Activation %", color="Activation %",
        color_continuous_scale=["#FF5252", "#FFB300", "#00E676"],
        template=PLOTLY_TEMPLATE, text=health["Activation %"].round(1),
    )
    fig.update_layout(height=340, margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------- CUSTOMER TAB ----
with tab_customer:
    st.markdown('<p class="section-title">Customer Wise Summary</p>', unsafe_allow_html=True)

    cust_summary = (
        df.groupby("Customer Name")
        .agg(
            Terminals=("Terminal Name", "count"),
            Activated=("Modem Status", lambda s: (s == "Activated").sum()),
            DA=("Modem Status", lambda s: (s == "D/A").sum()),
        )
        .reset_index()
        .rename(columns={"DA": "D/A"})
        .sort_values("Terminals", ascending=False)
    )

    top_n = st.slider("Show top N customers", 5, max(5, len(cust_summary)), min(15, max(5, len(cust_summary))))
    view = cust_summary.head(top_n)

    fig = px.bar(
        view, x="Customer Name", y=["Activated", "D/A"], barmode="stack",
        color_discrete_map={"Activated": "#00E676", "D/A": "#FF5252"},
        template=PLOTLY_TEMPLATE,
    )
    fig.update_layout(height=420, margin=dict(t=10, b=10, l=10, r=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        cust_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Terminals": st.column_config.NumberColumn(format="%d"),
            "Activated": st.column_config.NumberColumn(format="%d"),
            "D/A": st.column_config.NumberColumn(format="%d"),
        },
    )

# --------------------------------------------------------- DETAILS TAB -----
with tab_details:
    st.markdown('<p class="section-title">Terminal Details</p>', unsafe_allow_html=True)

    modem_search = st.text_input("🔍 Search by Modem Number", "")
    detail_df = df.copy()
    if modem_search:
        detail_df = detail_df[
            detail_df["Modem Number"].astype(str).str.contains(modem_search, case=False, na=False)
        ]

    st.dataframe(
        detail_df,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Down MIR": st.column_config.NumberColumn(format="%.1f"),
            "Up MIR": st.column_config.NumberColumn(format="%.1f"),
            "Down CIR": st.column_config.NumberColumn(format="%.1f"),
            "Up CIR": st.column_config.NumberColumn(format="%.1f"),
        },
    )
    st.caption(f"Showing {len(detail_df):,} of {len(df):,} filtered terminals (use sidebar + search box to narrow further).")

# -------------------------------------------------------- BANDWIDTH TAB ----
with tab_bw:
    st.markdown('<p class="section-title">Bandwidth Summary</p>', unsafe_allow_html=True)

    total_down_mir = df["Down MIR"].sum(skipna=True)
    total_up_mir = df["Up MIR"].sum(skipna=True)
    avg_down_mir = df["Down MIR"].mean(skipna=True)
    avg_up_mir = df["Up MIR"].mean(skipna=True)

    b1, b2, b3, b4 = st.columns(4)
    kpi_card(b1, "Total Down MIR", f"{total_down_mir:,.1f}", "Mbps aggregate", "kpi-blue")
    kpi_card(b2, "Total Up MIR", f"{total_up_mir:,.1f}", "Mbps aggregate", "kpi-blue")
    kpi_card(b3, "Avg Down MIR", f"{avg_down_mir:,.2f}" if pd.notna(avg_down_mir) else "—", "per terminal", "kpi-purple")
    kpi_card(b4, "Avg Up MIR", f"{avg_up_mir:,.2f}" if pd.notna(avg_up_mir) else "—", "per terminal", "kpi-purple")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<p class="section-title">Customer-wise Bandwidth (Down + Up MIR)</p>', unsafe_allow_html=True)
    bw_cust = (
        df.groupby("Customer Name")[["Down MIR", "Up MIR", "Down CIR", "Up CIR"]]
        .sum(min_count=1)
        .reset_index()
        .sort_values("Down MIR", ascending=False)
    )
    fig = px.bar(
        bw_cust.head(20), x="Customer Name", y=["Down MIR", "Up MIR"], barmode="group",
        color_discrete_sequence=["#00D4FF", "#B388FF"], template=PLOTLY_TEMPLATE,
    )
    fig.update_layout(height=420, margin=dict(t=10, b=10, l=10, r=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(bw_cust, use_container_width=True, hide_index=True)

# =============================================================================
# 9. FOOTER
# =============================================================================
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f"""
    <div style="text-align:center; color:#5C6470; font-size:11.5px; padding:14px 0;
                border-top:1px solid #1F2937;">
        {COMPANY_NAME} · NOC Terminal Monitoring Dashboard · Auto-refresh every {refresh_seconds}s ·
        Data source: Google Sheets (live) · Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    """,
    unsafe_allow_html=True,
)
