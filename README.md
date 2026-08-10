# 🛰️ NOC Terminal Monitoring Dashboard

A free, live, web-based dashboard built with **Python + Streamlit** that reads
satellite terminal data directly from Google Sheets, combines multiple tabs,
and auto-refreshes so anyone with the link always sees the latest data —
no Excel, no Google Sheets, no software install, no login.

---

## 1. Folder Structure

```
noc-dashboard/
├── app.py                   # main dashboard app (everything lives here)
├── requirements.txt         # Python dependencies
├── .streamlit/
│   └── config.toml          # dark NOC theme
└── README.md                 # this file
```

---

## 2. How data flows (no paid API needed)

Instead of the paid/complex Google Sheets API + service account route, this
project uses Google's **free built-in CSV export URL**:

```
https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/export?format=csv&gid=<GID>
```

Pandas reads that URL directly like a CSV file. Every time the dashboard
refreshes, it re-downloads the CSV, so it always reflects the sheet's current
values — completely free, no API key, no quota limits to worry about for
normal use.

**Requirement:** the sheet must be shared as **"Anyone with the link → Viewer"**
(File → Share → General access), since Streamlit Community Cloud runs
anonymously with no Google login.

> If your data is sensitive and you don't want it link-shareable, see
> **Section 6 — Private sheet option (service account)** at the bottom.

---

## 3. Where to put your Google Sheet URLs / IDs

Open `app.py` and find the **CONFIG** section near the top:

```python
SPREADSHEET_ID = "1GQP3xI9bFU36LM4PpYBxl7fMcqcsoyKM"

SHEET_SOURCES = [
    {"label": "HS4 & ABS-2A Sites", "spreadsheet_id": SPREADSHEET_ID, "gid": "95063111"},
    {"label": "NSS-12 Sites",        "spreadsheet_id": SPREADSHEET_ID, "gid": "1394382842"},
    {"label": "Third Sheet",         "spreadsheet_id": SPREADSHEET_ID, "gid": "194083809"},
]
```

How to read a Google Sheet URL:

```
https://docs.google.com/spreadsheets/d/1GQP3xI9bFU36LM4PpYBxl7fMcqcsoyKM/edit?gid=95063111#gid=95063111
                                        └────────── SPREADSHEET_ID ─────────┘         └── GID ──┘
```

- **spreadsheet_id** — the long string between `/d/` and `/edit`
- **gid** — the number after `gid=` (identifies which tab)

I've already filled in your first two sheets (HS4 & ABS-2A, NSS-12) using the
IDs/GIDs you provided. I added an entry for your **third sheet** using the
GID `194083809` you mentioned — I assumed it's a different tab in the *same*
spreadsheet file. If it's actually in a **different spreadsheet file**, just
give that entry its own `spreadsheet_id` instead of reusing `SPREADSHEET_ID`.

To add a 4th, 5th, etc. sheet later, just add another dictionary to the list.

---

## 4. How the data cleaning works

Your sheets aren't a clean flat table — they have summary boxes at the top,
section title rows like "AKC Terminals" / "ALI BGP Terminals", and blank
spacer rows. The app handles this automatically:

1. **Header detection** — scans the first ~60 rows for the one containing
   both "Customer Name" and "Modem" — that's treated as the real header row.
2. **Column mapping** — matches header text by keyword (case-insensitive) to
   standardized columns: Customer Name, Terminal Name, Modem Number, Network,
   Modem Status, Down/Up MIR, Down/Up CIR. This means small header wording
   changes (e.g. "Modem#" vs "Modem #") won't break it.
3. **Row cleanup** — drops blank rows and section-title rows (they have no
   Customer Name value), and drops any leftover junk rows with neither a
   modem number nor a status.
4. **Value normalization** — `A/C` → `Activated`, `D/A` → `D/A`; network
   names like `HS-4`, `hs4`, `Nss-12`, `NSS-12` are normalized to consistent
   labels (`HS4`, `NSS-12`, etc.); MIR/CIR values like `"2,000"` are
   converted to real numbers.
5. **Combine** — all cleaned sheets are concatenated into one dataframe, with
   a `Source Sheet` column so you can always trace a row back to its tab.

If a sheet's structure changes so much that the header can't be found, or a
sheet fails to load (wrong ID, not shared publicly, network issue), the
dashboard **does not crash** — it shows a warning banner listing exactly
which sheet had a problem and continues showing data from the sheets that
did load.

---

## 5. Run it locally first (recommended before deploying)

```bash
cd noc-dashboard
pip install -r requirements.txt
streamlit run app.py
```

This opens `http://localhost:8501` in your browser. Confirm the KPI cards,
charts, and tables look right using your real sheet data before deploying.

---

## 6. Deploy for free — Streamlit Community Cloud

This gives you a permanent public URL like `https://your-app.streamlit.app`
that your boss/team can open in any browser, on any device, with zero setup.

### Step 1 — Push the project to GitHub
1. Create a free GitHub account if you don't have one: https://github.com
2. Create a new **public or private** repository, e.g. `noc-dashboard`
3. Upload these files to it (`app.py`, `requirements.txt`, `.streamlit/config.toml`, `README.md`) —
   either via the GitHub web UI ("Add file → Upload files") or via git:
   ```bash
   cd noc-dashboard
   git init
   git add .
   git commit -m "Initial NOC dashboard"
   git branch -M main
   git remote add origin https://github.com/<your-username>/noc-dashboard.git
   git push -u origin main
   ```

### Step 2 — Deploy on Streamlit Community Cloud (free)
1. Go to https://share.streamlit.io and sign in with your GitHub account
2. Click **"Create app"** → **"Deploy a public app from GitHub"**
3. Select:
   - Repository: `<your-username>/noc-dashboard`
   - Branch: `main`
   - Main file path: `app.py`
4. Click **Deploy**. Streamlit installs `requirements.txt` automatically and
   builds your app.
5. After a minute or two, you'll get your live URL:
   ```
   https://your-app-name.streamlit.app
   ```

### Step 3 — Share it
Send that URL to your boss/team. Anyone who opens it sees the live dashboard
in their browser — no Python, no GitHub account, no Excel, nothing to
install.

### Updating the dashboard later
Any time you push a new commit to the `main` branch on GitHub, Streamlit
Community Cloud automatically redeploys the app with your changes within a
minute or two. You never touch the sheet data for code updates — the sheet
data itself refreshes live on every page load/auto-refresh cycle, completely
independent of code deployments.

---

## 7. Auto-refresh behavior

- The sidebar lets each viewer pick a refresh interval (30s / 60s / 2min / 5min).
- Under the hood, `streamlit_autorefresh` reruns the page on that interval.
- Data is cached for 60 seconds server-side (`st.cache_data(ttl=60)`) so the
  app isn't hammering Google with a request on every single browser tick —
  but it also means a change in the sheet appears within at most ~60 seconds,
  or immediately if someone clicks **"↻ Refresh now"** in the sidebar (which
  clears the cache).

Example: change a terminal's Modem Status in Google Sheets from `A/C` to
`D/A`, save it, and within one refresh cycle the dashboard's KPI cards,
charts, and table all reflect the new status automatically.

---

## 8. Private sheet option (optional, still free)

If you'd rather not make the sheet link-shareable, you can use a free Google
**service account** instead of the CSV export method:

1. Create a free Google Cloud project → enable the **Google Sheets API**.
2. Create a **Service Account**, generate a JSON key.
3. Share your Google Sheet with the service account's email address
   (found inside the JSON key) as **Viewer**.
4. Add `gspread` and `google-auth` to `requirements.txt`.
5. Store the JSON key contents in Streamlit Cloud's **Secrets** (Settings →
   Secrets in the Streamlit Cloud dashboard) — never commit the key file to
   GitHub.
6. Replace `fetch_raw_sheet()` in `app.py` with a `gspread` read using the
   service account credentials from `st.secrets`.

This is more setup but keeps the sheet fully private. Happy to write this
version out in full if you decide you need it — just ask.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "No terminal data could be loaded" | Sheet not shared publicly | Share → Anyone with the link → Viewer |
| One sheet shows ⚠️ in sidebar | Header row not detected | Confirm that sheet still has a row containing "Customer Name" and "Modem #" |
| Numbers look wrong / blank | MIR/CIR columns renamed or moved | Check header text still contains "MIR"/"CIR" keywords |
| Dashboard looks stale | Auto-refresh toggled off | Turn "Auto" toggle on in sidebar, or click "Refresh now" |
