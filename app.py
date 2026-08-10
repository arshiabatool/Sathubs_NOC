"""
NOC Terminal Monitoring Dashboard
==================================
Reads satellite terminal data live from Google Sheets, cleans/normalizes it,
combines multiple sheets, and displays a professional NOC-style dashboard
in Streamlit.

Author: Built for NOC operations team
"""

import re
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# =====================================================================================
# 1. CONFIGURATION  ---  EDIT THIS SECTION TO POINT TO YOUR GOOGLE SHEETS
# =====================================================================================
# For each source sheet you want to combine, add an entry below with:
#   - "label"         : friendly name shown in the dashboard
#   - "spreadsheet_id" : the long ID from the sheet URL
#                        e.g. https://docs.google.com/spreadsheets/d/<THIS PART>/edit
#   - "gid"           : the tab/sheet id, taken from ...#gid=<THIS PART> in the URL
#
# IMPORTANT: The Google Sheet must be shared as "Anyone with the link -> Viewer"
# for this CSV-export method to work without any login or paid API.
# (File > Share > General access > Anyone with the link)
# =====================================================================================

SPREADSHEET_ID = "1GQP3xI9bFU36LM4PpYBxl7fMcqcsoyKM"  # same file for all three tabs below

SHEET_SOURCES = [
    {"label": "HS4 & ABS-2A Sites", "spreadsheet_id": SPREADSHEET_ID, "gid": "95063111"},
    {"label": "NSS-12 Sites",        "spreadsheet_id": SPREADSHEET_ID, "gid": "1394382842"},
    {"label": "Third Sheet",         "spreadsheet_id": SPREADSHEET_ID, "gid": "194083809"},
]

# Auto-refresh interval choices (seconds) shown in the sidebar
REFRESH_CHOICES = {"30 seconds": 30, "60 seconds": 60, "2 minutes": 120, "5 minutes": 300}

APP_TITLE = "Sathubs NOC Dashboard"

# =====================================================================================
# 2. PAGE CONFIG + STYLE
# =====================================================================================
st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}

.block-container {padding-top: 1.4rem; padding-bottom: 2rem;}

h1, h2, h3 { color: #E6EDF3; }

/* Slim header */
.block-container {padding-top: 1rem; padding-bottom: 2rem;}

/* Make header bar thinner */
h1 { 
    font-size: 1.8rem !important; 
    margin-top: -0.3rem !important;
    margin-bottom: 0rem !important;
}

/* Logo and title alignment */
[data-testid="column"] {
    display: flex;
    align-items: center;
}

.kpi-card {
    background: linear-gradient(145deg, #12233d, #0c1a2e);
    border: 1px solid #1f3a5f;
    border-radius: 14px;
    padding: 18px 16px;
    text-align: center;
    box-shadow: 0 4px 14px rgba(0,0,0,0.35);
}
.kpi-value {
    font-size: 2.1rem;
    font-weight: 800;
    color: #ffffff;
    margin: 4px 0 2px 0;
}
.kpi-label {
    font-size: 0.82rem;
    color: #9fb4cc;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.kpi-activated .kpi-value { color: #3ddc84; }
.kpi-da .kpi-value { color: #ff5c5c; }
.kpi-total .kpi-value { color: #4ea8ff; }

.status-pill {
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
}
.status-live {
    background: #123d24; color: #3ddc84; border: 1px solid #3ddc84;
}

.section-divider {
    margin-top: 0.4rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid #21344d;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =====================================================================================
# 3. DATA LOADING + CLEANING
# =====================================================================================

def build_csv_url(spreadsheet_id: str, gid: str) -> str:
    """Builds the public CSV export URL for a given Google Sheet tab."""
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


def fetch_raw_sheet(spreadsheet_id: str, gid: str) -> pd.DataFrame:
    """Fetches a sheet tab as a raw, headerless dataframe (position-based)."""
    url = build_csv_url(spreadsheet_id, gid)
    df_raw = pd.read_csv(url, header=None, dtype=str, keep_default_na=False, on_bad_lines="skip")
    return df_raw


# Keywords used to auto-detect the real header row/columns, since sheets contain
# title rows, summary blocks, and blank rows above the actual data table.
COLUMN_KEYWORDS = {
    "Customer Name": ["customer name"],
    "Terminal Name": ["new names", "terminal name", "remotes", "service package"],
    "Modem Number": ["modem #", "modem#", "modem no", "modem number"],
    "Down MIR": ["down mir"],
    "Up MIR": ["up mir"],
    "Down CIR": ["down cir"],
    "Up CIR": ["up cir"],
    "Network": ["network"],
    "Modem Status": ["modem status", "status"],
}


def find_header_row(df_raw: pd.DataFrame) -> int:
    """Scans rows to find the one that looks like the real column header row."""
    for i in range(min(len(df_raw), 60)):  # header is always near the top; cap the scan
        row_vals = [str(v).strip().lower() for v in df_raw.iloc[i].tolist()]
        has_customer = any("customer name" in v for v in row_vals)
        has_modem = any(("modem" in v) for v in row_vals)
        if has_customer and has_modem:
            return i
    return -1


def map_columns(header_row: list) -> dict:
    """Maps raw header text (by keyword match) to standardized column names."""
    mapping = {}
    for idx, raw_name in enumerate(header_row):
        name_lower = str(raw_name).strip().lower()
        if not name_lower:
            continue
        for standard_name, keywords in COLUMN_KEYWORDS.items():
            # "Modem Status" vs "Modem Number" both contain 'modem' - be specific
            if standard_name == "Modem Number" and "status" in name_lower:
                continue
            if standard_name == "Modem Status" and ("#" in name_lower or "no" in name_lower):
                continue
            if any(kw in name_lower for kw in keywords):
                mapping[idx] = standard_name
                break
    return mapping


def to_numeric_clean(series: pd.Series) -> pd.Series:
    """Converts strings like '2,000' or ' 512 ' into numeric, invalid -> NaN."""
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace({"": None, "nan": None, "-": None})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_status(value: str) -> str:
    v = str(value).strip().lower().replace(" ", "")
    if v in ("a/c", "ac", "active", "activated"):
        return "Activated"
    if v in ("d/a", "da", "deactivated", "deactive", "inactive"):
        return "D/A"
    if v == "" or v == "nan":
        return "Unknown"
    return value.strip().title()


NETWORK_CANONICAL = {
    "hs4": "HS4",
    "hs-4": "HS4",
    "abs2a": "ABS-2A",
    "abs-2a": "ABS-2A",
    "nss12": "NSS-12",
    "nss-12": "NSS-12",
    "asiasat5a": "Asiasat 5A",
    "asiasat 5a": "Asiasat 5A",
    "as-5a": "Asiasat 5A",
}


def normalize_network(value: str) -> str:
    v = str(value).strip().lower().replace(" ", "").replace("_", "")
    for key, canonical in NETWORK_CANONICAL.items():
        if v == key.replace(" ", "").replace("-", ""):
            return canonical
        if v == key:
            return canonical
    v_spaced = str(value).strip().lower()
    for key, canonical in NETWORK_CANONICAL.items():
        if v_spaced == key:
            return canonical
    cleaned = str(value).strip()
    return cleaned if cleaned and cleaned.lower() != "nan" else "Unknown"


def clean_sheet(df_raw: pd.DataFrame, source_label: str) -> pd.DataFrame:
    """Turns a raw positional dataframe into a clean, standardized terminal table."""
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    header_idx = find_header_row(df_raw)
    if header_idx == -1:
        return pd.DataFrame()  # couldn't detect structure; caller will warn the user

    header_row = df_raw.iloc[header_idx].tolist()
    col_map = map_columns(header_row)
    if not col_map:
        return pd.DataFrame()

    data = df_raw.iloc[header_idx + 1:].reset_index(drop=True)

    standardized = pd.DataFrame()
    for idx, standard_name in col_map.items():
        if idx < data.shape[1]:
            standardized[standard_name] = data.iloc[:, idx]

    # Ensure all expected columns exist even if a sheet is missing one
    for col in COLUMN_KEYWORDS.keys():
        if col not in standardized.columns:
            standardized[col] = None

    # Drop blank rows and section-title rows (e.g. "AKC Terminals") which have
    # no Customer Name value
    standardized["Customer Name"] = standardized["Customer Name"].astype(str).str.strip()
    standardized = standardized[
        (standardized["Customer Name"] != "") & (standardized["Customer Name"].str.lower() != "nan")
    ]

    if standardized.empty:
        return standardized

    # Also drop rows with no Modem Status AND no Modem Number (leftover junk rows)
    standardized["Modem Number"] = standardized["Modem Number"].astype(str).str.strip()
    standardized["Modem Status"] = standardized["Modem Status"].astype(str).str.strip()
    standardized = standardized[
        ~((standardized["Modem Number"].isin(["", "nan"])) & (standardized["Modem Status"].isin(["", "nan"])))
    ]

    # Normalize values
    standardized["Modem Status"] = standardized["Modem Status"].apply(normalize_status)
    standardized["Network"] = standardized["Network"].apply(normalize_network)
    standardized["Customer Name"] = standardized["Customer Name"].str.strip()
    standardized["Terminal Name"] = standardized["Terminal Name"].astype(str).str.strip()
    standardized["Modem Number"] = standardized["Modem Number"].str.strip()

    for col in ["Down MIR", "Up MIR", "Down CIR", "Up CIR"]:
        standardized[col] = to_numeric_clean(standardized[col])

    standardized["Source Sheet"] = source_label
    standardized = standardized.reset_index(drop=True)
    return standardized


@st.cache_data(ttl=60, show_spinner=False)
def load_all_data(sources: tuple) -> tuple:
    """
    Fetches + cleans + combines all configured sheets.
    Returns: (combined_dataframe, list_of_errors, list_of_loaded_sheet_labels)
    """
    frames = []
    errors = []
    loaded = []

    for src in sources:
        label = src["label"]
        try:
            raw = fetch_raw_sheet(src["spreadsheet_id"], src["gid"])
            cleaned = clean_sheet(raw, label)
            if cleaned.empty:
                errors.append(
                    f"'{label}': sheet loaded but no terminal rows could be detected. "
                    f"Check that the header row still contains 'Customer Name' and 'Modem #'."
                )
            else:
                frames.append(cleaned)
                loaded.append(label)
        except Exception as e:  # network error, permission error, sheet moved, etc.
            errors.append(f"'{label}': could not load sheet ({e}). Is it shared as 'Anyone with the link'?")

    if frames:
        combined = pd.concat(frames, ignore_index=True)
    else:
        combined = pd.DataFrame(
            columns=[
                "Customer Name", "Terminal Name", "Modem Number", "Network",
                "Modem Status", "Down MIR", "Up MIR", "Down CIR", "Up CIR", "Source Sheet",
            ]
        )

    return combined, errors, loaded


# =====================================================================================
# 4. SIDEBAR — refresh controls + filters
# =====================================================================================
with st.sidebar:
    st.markdown("## 🛰️ NOC Control Panel")
    st.caption("Live Google Sheets terminal monitoring")

    st.markdown("### 🔄 Auto Refresh")
    refresh_label = st.selectbox("Refresh interval", list(REFRESH_CHOICES.keys()), index=1)
    refresh_seconds = REFRESH_CHOICES[refresh_label]

    col_a, col_b = st.columns(2)
    with col_a:
        manual_refresh = st.button("↻ Refresh now", use_container_width=True)
    with col_b:
        auto_on = st.toggle("Auto", value=True)

    if manual_refresh:
        load_all_data.clear()

    if auto_on:
        st_autorefresh(interval=refresh_seconds * 1000, key="auto_refresh_timer")

    st.markdown("---")

# Load data (cached)
df, load_errors, loaded_sheets = load_all_data(tuple(SHEET_SOURCES))

with st.sidebar:
    st.markdown("### 📄 Data Sources")
    for src in SHEET_SOURCES:
        ok = src["label"] in loaded_sheets
        icon = "✅" if ok else "⚠️"
        st.markdown(f"{icon} {src['label']}")

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not df.empty:
        st.markdown("---")
        st.markdown("### 🔍 Filters (Details Table)")
        customers = sorted([c for c in df["Customer Name"].dropna().unique() if c])
        networks = sorted([n for n in df["Network"].dropna().unique() if n])
        statuses = sorted([s for s in df["Modem Status"].dropna().unique() if s])

        f_customer = st.multiselect("Customer", customers, default=[])
        f_network = st.multiselect("Network", networks, default=[])
        f_status = st.multiselect("Status", statuses, default=[])
        f_modem_search = st.text_input("Modem Number contains")

# =====================================================================================
# =====================================================================================
# 5. HEADER WITH SATHUBS LOGO
# =====================================================================================

# Create two columns for logo and title
col_logo, col_title = st.columns([1, 10])

with col_logo:
    try:
        # Adjust width (50-80px works well for a slim header)
        st.image("sathubs_logo.png", width=60)
    except:
        st.markdown("### 🛰️")  # Fallback

with col_title:
    st.markdown(f"# {APP_TITLE}")
    st.markdown(
        '<span class="status-pill status-live">● LIVE</span>&nbsp;&nbsp;'
        f'<span style="color:#9fb4cc;">Auto-refreshing every {refresh_seconds}s from Google Sheets</span>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
# 6. KPI CARDS (Overview)
# =====================================================================================
total_terminals = len(df)
total_activated = int((df["Modem Status"] == "Activated").sum())
total_da = int((df["Modem Status"] == "D/A").sum())
hs4_count = int((df["Network"] == "HS4").sum())
abs2a_count = int((df["Network"] == "ABS-2A").sum())
nss12_count = int((df["Network"] == "NSS-12").sum())


def kpi_card(label, value, css_class=""):
    st.markdown(
        f"""
        <div class="kpi-card {css_class}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    kpi_card("Total Terminals", total_terminals, "kpi-total")
with k2:
    kpi_card("Activated", total_activated, "kpi-activated")
with k3:
    kpi_card("D/A", total_da, "kpi-da")
with k4:
    kpi_card("HS4", hs4_count)
with k5:
    kpi_card("ABS-2A", abs2a_count)
with k6:
    kpi_card("NSS-12", nss12_count)

st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

# =====================================================================================
# 7. TABS
# =====================================================================================
tab_status, tab_network, tab_customer, tab_details, tab_bandwidth = st.tabs(
    ["📊 Terminal Status", "🌐 Network Distribution", "👥 Customer Summary",
     "📋 Terminal Details", "📶 Bandwidth Summary"]
)

STATUS_COLORS = {"Activated": "#3ddc84", "D/A": "#ff5c5c", "Unknown": "#9fb4cc"}
NETWORK_COLORS = px.colors.qualitative.Set2

# ---- TAB: Terminal Status ----------------------------------------------------------
with tab_status:
    st.subheader("Activated vs D/A")
    status_counts = df["Modem Status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]

    c1, c2 = st.columns(2)
    with c1:
        fig_pie = px.pie(
            status_counts, names="Status", values="Count", hole=0.5,
            color="Status", color_discrete_map=STATUS_COLORS,
            title="Status Distribution",
        )
        fig_pie.update_traces(textinfo="value+percent")
        fig_pie.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pie, use_container_width=True)
    with c2:
        fig_bar = px.bar(
            status_counts, x="Status", y="Count", color="Status",
            color_discrete_map=STATUS_COLORS, text="Count",
            title="Status Count",
        )
        fig_bar.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("##### Status Breakdown by Network")
    status_by_net = df.groupby(["Network", "Modem Status"]).size().reset_index(name="Count")
    fig_stack = px.bar(
        status_by_net, x="Network", y="Count", color="Modem Status",
        color_discrete_map=STATUS_COLORS, barmode="stack", text="Count",
    )
    fig_stack.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_stack, use_container_width=True)

# ---- TAB: Network Distribution ------------------------------------------------------
with tab_network:
    st.subheader("Terminals per Network / Satellite")
    net_counts = df["Network"].value_counts().reset_index()
    net_counts.columns = ["Network", "Count"]

    c1, c2 = st.columns(2)
    with c1:
        fig_net_pie = px.pie(
            net_counts, names="Network", values="Count", hole=0.4,
            color_discrete_sequence=NETWORK_COLORS, title="Network Share",
        )
        fig_net_pie.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_net_pie, use_container_width=True)
    with c2:
        fig_net_bar = px.bar(
            net_counts.sort_values("Count", ascending=True), x="Count", y="Network",
            orientation="h", color="Network", color_discrete_sequence=NETWORK_COLORS,
            text="Count", title="Terminal Count by Network",
        )
        fig_net_bar.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(fig_net_bar, use_container_width=True)

    st.dataframe(net_counts, use_container_width=True, hide_index=True)

# ---- TAB: Customer Summary -----------------------------------------------------------
with tab_customer:
    st.subheader("Customer-wise Terminal Summary")
    cust_summary = (
        df.groupby("Customer Name")
        .agg(
            Total_Terminals=("Customer Name", "count"),
            Activated=("Modem Status", lambda s: (s == "Activated").sum()),
            DA=("Modem Status", lambda s: (s == "D/A").sum()),
        )
        .reset_index()
        .rename(columns={"DA": "D/A"})
        .sort_values("Total_Terminals", ascending=False)
    )

    fig_cust = go.Figure()
    fig_cust.add_bar(name="Activated", x=cust_summary["Customer Name"], y=cust_summary["Activated"],
                      marker_color=STATUS_COLORS["Activated"])
    fig_cust.add_bar(name="D/A", x=cust_summary["Customer Name"], y=cust_summary["D/A"],
                      marker_color=STATUS_COLORS["D/A"])
    fig_cust.update_layout(
        barmode="stack", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
        title="Terminals per Customer (Activated vs D/A)", xaxis_title="", yaxis_title="Terminals",
    )
    st.plotly_chart(fig_cust, use_container_width=True)

    st.dataframe(
        cust_summary.rename(columns={"Total_Terminals": "Total Terminals"}),
        use_container_width=True, hide_index=True,
    )

# ---- TAB: Terminal Details ------------------------------------------------------------
with tab_details:
    st.subheader("Searchable Terminal Details")

    filtered = df.copy()
    if f_customer:
        filtered = filtered[filtered["Customer Name"].isin(f_customer)]
    if f_network:
        filtered = filtered[filtered["Network"].isin(f_network)]
    if f_status:
        filtered = filtered[filtered["Modem Status"].isin(f_status)]
    if f_modem_search:
        filtered = filtered[filtered["Modem Number"].str.contains(f_modem_search.strip(), case=False, na=False)]

    st.caption(f"Showing {len(filtered)} of {len(df)} terminals")
    display_cols = [
        "Customer Name", "Terminal Name", "Modem Number", "Network",
        "Modem Status", "Down MIR", "Up MIR", "Down CIR", "Up CIR", "Source Sheet",
    ]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True, height=520)

    csv_export = filtered[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download filtered data (CSV)", csv_export, "terminal_details.csv", "text/csv")

# ---- TAB: Bandwidth Summary ------------------------------------------------------------
with tab_bandwidth:
    st.subheader("Bandwidth Summary")

    total_down_mir = df["Down MIR"].sum(skipna=True)
    total_up_mir = df["Up MIR"].sum(skipna=True)
    avg_down_mir = df["Down MIR"].mean(skipna=True)
    avg_up_mir = df["Up MIR"].mean(skipna=True)

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        kpi_card("Total Down MIR", f"{total_down_mir:,.0f}")
    with b2:
        kpi_card("Total Up MIR", f"{total_up_mir:,.0f}")
    with b3:
        kpi_card("Avg Down MIR", f"{avg_down_mir:,.0f}")
    with b4:
        kpi_card("Avg Up MIR", f"{avg_up_mir:,.0f}")

    st.markdown("##### Customer-wise Bandwidth")
    bw_summary = (
        df.groupby("Customer Name")
        .agg(
            Total_Down_MIR=("Down MIR", "sum"),
            Total_Up_MIR=("Up MIR", "sum"),
            Total_Down_CIR=("Down CIR", "sum"),
            Total_Up_CIR=("Up CIR", "sum"),
        )
        .reset_index()
        .sort_values("Total_Down_MIR", ascending=False)
    )
    bw_summary = bw_summary.rename(columns={
        "Total_Down_MIR": "Total Down MIR", "Total_Up_MIR": "Total Up MIR",
        "Total_Down_CIR": "Total Down CIR", "Total_Up_CIR": "Total Up CIR",
    })

    fig_bw = px.bar(
        bw_summary, x="Customer Name", y=["Total Down MIR", "Total Up MIR"],
        barmode="group", title="Down/Up MIR by Customer",
    )
    fig_bw.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_bw, use_container_width=True)

    st.dataframe(bw_summary, use_container_width=True, hide_index=True)

# =====================================================================================
# 8. FOOTER
# =====================================================================================
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.caption(
    f"NOC Terminal Monitoring Dashboard · Data combined from {len(loaded_sheets)}/{len(SHEET_SOURCES)} "
    f"sheets · Cache refresh every 60s · Page auto-refresh every {refresh_seconds}s"
)
