# Sathubs LLC — NOC Terminal Monitoring Dashboard

A free, live, web-based dashboard (Python + Streamlit) that reads terminal data
directly from Google Sheets and gives anyone with the link a real-time NOC view —
no Excel, no Google Sheets, no software install required for viewers.

---

## 1. Folder structure

```
noc-dashboard/
├── app.py                     # Main dashboard app (all logic + UI)
├── requirements.txt           # Python dependencies
├── logo.jpg                   # <-- PUT YOUR LOGO HERE (same folder as app.py)
└── .streamlit/
    └── config.toml            # Dark professional theme
```

> **Important:** `logo.jpg` must sit in the exact same folder as `app.py` in your
> GitHub repo (the repo root, not a subfolder) unless you change `LOGO_FILENAME`
> in `app.py`. If the file is missing, the header shows a clean "SL" placeholder
> instead of crashing.

---

## 2. Connect your Google Sheet (free method — CSV export, no API key)

This dashboard reads each sheet tab using Google's built-in CSV export link, so
you don't need a Google Cloud project, API key, or service account.

**Step 1 — Share the sheet:**
Open your Google Sheet → **Share** → **General access** → set to
**"Anyone with the link" → Viewer**. (Data stays read-only; nobody can edit it
via this link.)

**Step 2 — Get the Spreadsheet ID and each tab's `gid`:**
From a URL like:
```
https://docs.google.com/spreadsheets/d/1GQP3xI9bFU36LM4PpYBxl7fMcqcsoyKM/edit?gid=95063111#gid=95063111
                                        └──────────── SPREADSHEET ID ───────────┘        └ GID ┘
```

**Step 3 — Edit the config block at the top of `app.py`:**
```python
SPREADSHEET_ID = "1GQP3xI9bFU36LM4PpYBxl7fMcqcsoyKM"

SHEETS = {
    "HS4 & ABS-2A Sites": "95063111",
    "NSS-12 Sites":       "1394382842",
    "Additional Sites":   "194083809",
}
```
Add, remove, or rename entries in `SHEETS` to match your own tabs — the
dashboard automatically combines however many you list.

> If your sheet is private and you don't want to make it link-viewable, the
> alternative is a Google Service Account + `gspread` (paid-free tier, more
> setup). Ask if you want that version — the CSV method above is simpler and
> fully free, which is why it's used here.

---

## 3. What the dashboard does with messy sheets

Real sheets rarely start with a clean header on row 1. The cleaning pipeline in
`app.py` automatically:
- Scans the first ~20 rows to find the real header row (skips title/banner rows)
- Drops fully blank rows and columns
- Drops stray "section title" rows (rows with only 1 filled cell)
- Maps many possible column name variants (e.g. "Modem No.", "S/N", "Modem Sr No")
  to standard fields: `Customer Name`, `Terminal Name`, `Modem Number`, `Network`,
  `Modem Status`, `Down MIR`, `Up MIR`, `Down CIR`, `Up CIR`
- Normalizes status values (`A/C`, `Active`, `ACT` → **Activated**; `D/A`,
  `Deactive`, `Inactive` → **D/A**)
- Converts bandwidth columns to numbers safely (non-numeric text is ignored)
- If a sheet has no `Network` column, it tags all its rows with the sheet's
  label from `SHEETS` (e.g. "NSS-12 Sites")

If your real column headers don't match automatically, just add the exact text
you use to the `COLUMN_ALIASES` dictionary near the top of `app.py`.

### Closed customer & network lists

Your sheets mix real terminal rows in with summary blocks, section-title rows
("AKC Terminals"), and a trailing Terminal#/ESID lookup table that don't share
the same columns as the real data. To reliably tell these apart, `app.py`
uses two lists you gave us:

```python
KNOWN_CUSTOMERS = {
    "akc": "AKC", "azh": "AZH", "ali": "ALI (BGP)",
    "shaheen": "Shaheen Shah (BGP)", "starwin": "Starwin",
    "xn": "XN", "sbg": "SBG-Hadi", "hadi": "SBG-Hadi",
}

KNOWN_NETWORKS = {
    "hs4": "HS4", "hs-4": "HS4", "abs-2a": "ABS-2A",
    "nss-12": "NSS-12", "asiasat 5a": "AsiaSat 5A", ...
}
```

**Any row whose Customer Name doesn't match this list is dropped as junk** —
this is what removes the summary blocks, section titles, and the ESID table
automatically. **If you add a new customer**, add them to `KNOWN_CUSTOMERS` or
their rows will silently disappear from the dashboard. Networks that don't
match `KNOWN_NETWORKS` are *not* dropped — they show up under "Other" so you
notice them, rather than vanishing.

---

## 4. Run it locally (optional, to preview before sharing)

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```
It opens at `http://localhost:8501`.

---

## 5. Deploy for free — get a public URL your boss/team can open

### Step A — Push to GitHub
1. Create a new **public** (or private, both work) GitHub repository, e.g. `noc-dashboard`.
2. Upload all 3 items: `app.py`, `requirements.txt`, `logo.jpg`, and the
   `.streamlit/config.toml` file (keep the `.streamlit` folder).
3. Commit.

### Step B — Deploy on Streamlit Community Cloud (100% free)
1. Go to **https://share.streamlit.io** and sign in with your GitHub account.
2. Click **"New app"**.
3. Select your repository, branch (`main`), and set **Main file path** to `app.py`.
4. Click **Deploy**.
5. Streamlit builds the app and gives you a URL like:
   ```
   https://your-app-name.streamlit.app
   ```

### Step C — Share it
Send that URL to your boss/team. Anyone who opens it in a browser sees the
live dashboard — no Python, no GitHub account, no Excel, nothing to install.

---

## 6. Auto-refresh behavior

- Data is cached for the interval you choose in the sidebar (default 60s) —
  after that, the next page load/refresh pulls fresh data from Google Sheets.
- The page itself also auto-reruns on that same interval (via
  `streamlit-autorefresh`), so a viewer who leaves the tab open will see
  updates appear automatically — e.g. if a terminal's status changes from
  `A/C` to `D/A` in the sheet, it will show as **D/A** within one refresh cycle.
- A manual **"🔄 Refresh now"** button in the sidebar forces an immediate reload.

---

## 7. Dashboard sections

| Tab | Contents |
|---|---|
| 📊 Overview | KPI cards (total / activated / D-A / per-network counts), status pie, network bar, health alert banner |
| 🟢 Terminal Status | Activated vs D/A pie + bar, status breakdown by network |
| 🛰️ Network Distribution | Pie + treemap of terminals per network, per-network activation % health chart |
| 👥 Customer Summary | Stacked bar (Activated vs D/A) per customer + full summary table |
| 📋 Terminal Details | Full searchable/filterable table (Customer, Network, Status filters in sidebar; Modem Number search box) |
| 📶 Bandwidth Summary | Total/average Down & Up MIR, customer-wise bandwidth bar chart + table |

Global filters (Customer, Network, Status) live in the sidebar and apply to
every tab at once. A CSV export button in the sidebar lets you download the
currently loaded dataset.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| "No data could be loaded from any sheet" | Sheet isn't shared as "Anyone with the link — Viewer", or `SPREADSHEET_ID` / `gid` is wrong |
| A sheet loads but shows 0 rows | Its header row wasn't detected — check that column names roughly match the aliases in `COLUMN_ALIASES`, or add your exact header text there |
| Logo doesn't appear | Confirm `logo.jpg` is committed in the **same folder** as `app.py` in GitHub, exact filename/case match |
| Numbers look wrong for MIR/CIR | Check the sheet doesn't mix units (e.g. "2 Mbps" text) — the app extracts the first number it finds in each cell |
| Dashboard feels slow to refresh | Lower the refresh interval slider, but note very frequent refreshes (15s) increase load on Google's CSV endpoint |

---

## 9. Cost

Everything here is free:
- Streamlit Community Cloud hosting — free
- Google Sheets CSV export — free, no API key
- GitHub public/private repo — free

No paid software or subscriptions are required anywhere in this stack.
