"""
Pace Calculator page.

Shows each store's previous day's sales, projected monthly total, and
projected annual total, using a flat run-rate calculation against the
cached daily sales log (see sales_pace.py).

Add this file to your app's navigation the same way Commissions/
Transactions/Touch Tell are registered in app.py, and rename it to match
your existing pages' naming convention if needed.

NOTE ON store display names: this assumes each entry in stores_config.json
may have a "display_name" field to show instead of the raw store key. If it
doesn't, this just falls back to showing the store key itself - adjust
store_names below if you keep display names somewhere else (e.g. hardcoded
in stores_config.json under a different field, or in a separate mapping).

PASSWORD: set PACE_CALCULATOR_PASSWORD as an environment variable (locally
and on Railway, same pattern as your other env vars). There's also a
hardcoded fallback below for local use, same pattern used for
PACE_LOG_SHEET_ID in sales_pace.py - replace the placeholder with your own
password.
"""
import os
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from lightspeed_client import load_config
from sales_pace import compute_pace, read_daily_log, update_daily_log

PAGE_PASSWORD = os.getenv("PACE_CALCULATOR_PASSWORD", "PASTE_A_PASSWORD_HERE")

if "pace_calculator_unlocked" not in st.session_state:
    st.session_state.pace_calculator_unlocked = False

if not st.session_state.pace_calculator_unlocked:
    st.title("Sales Pace Calculator")
    with st.form("pace_password_form"):
        entered_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock")
    if submitted:
        if entered_password == PAGE_PASSWORD:
            st.session_state.pace_calculator_unlocked = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

st.title("Sales Pace Calculator")

config = load_config()
store_keys = list(config["stores"].keys())
store_names = {
    key: config["stores"][key].get("name", key) for key in store_keys
}

col1, col2 = st.columns(2)
with col1:
    if st.button("Reload from sheet"):
        st.cache_data.clear()
        st.success("Reloaded.")
with col2:
    if st.button("Fetch missing days from Lightspeed"):
        with st.spinner("Fetching any missing days from Lightspeed - this can take a while for stores with little/no history yet..."):
            added = update_daily_log(config, store_keys)
        st.success(f"Log updated - added {added} new day(s) of data.")
        st.cache_data.clear()


@st.cache_data(ttl=3600)
def _load_log():
    return read_daily_log()


df = _load_log()

if df.empty:
    st.info(
        "No sales data logged yet. Run backfill_pace_log.py once from your "
        "terminal, then click 'Reload from sheet' above."
    )
else:
    rows = []
    for store_key in store_keys:
        pace = compute_pace(df, store_key)
        as_of = pace["as_of"]
        rows.append({
            "store": store_names[store_key],
            # as_of_sort is a real sortable value (ISO date or empty string,
            # which sorts first); as_of_display is what's actually shown -
            # sorting on "7/9" vs "7/10" as plain text would misorder them.
            "as_of_sort": as_of.isoformat() if as_of else "",
            "as_of_display": f"{as_of.month}/{as_of.day}" if as_of else "-",
            "latest_sales": pace["yesterday_total"],
            "projected_monthly": pace["projected_monthly"],
            "projected_annual": pace["projected_annual"],
        })

    rows.sort(key=lambda row: row["store"])

    table_height = 90 + len(rows) * 45

    components.html(
        f"""
        <style>
        body {{ font-family: "Source Sans Pro", Arial, sans-serif; margin: 0; }}
        .pace-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .pace-table th {{
            font-weight: 700;
            text-align: left;
            padding: 8px 12px;
            border-bottom: 2px solid #444;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }}
        .pace-table th:hover {{
            color: #ff4b4b;
        }}
        .pace-table th .arrow {{
            font-size: 11px;
            opacity: 0.6;
            margin-left: 4px;
        }}
        .pace-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #333;
        }}
        .pace-table td.store-cell {{
            font-weight: 700;
        }}
        </style>
        <table class="pace-table" id="pace-table">
            <thead>
                <tr>
                    <th data-key="store" data-type="string">Store<span class="arrow"></span></th>
                    <th data-key="as_of_sort" data-type="string">As Of<span class="arrow"></span></th>
                    <th data-key="latest_sales" data-type="number">Latest Day's Sales<span class="arrow"></span></th>
                    <th data-key="projected_monthly" data-type="number">Projected Monthly Total<span class="arrow"></span></th>
                    <th data-key="projected_annual" data-type="number">Projected Annual Total<span class="arrow"></span></th>
                </tr>
            </thead>
            <tbody id="pace-table-body"></tbody>
        </table>
        <script>
            let rows = {json.dumps(rows)};
            let sortKey = "store";
            let sortAsc = true;

            function money(value) {{
                return "$" + value.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
            }}

            function render() {{
                const tbody = document.getElementById("pace-table-body");
                tbody.innerHTML = rows.map(r => (
                    "<tr>" +
                    "<td class='store-cell'>" + r.store + "</td>" +
                    "<td>" + r.as_of_display + "</td>" +
                    "<td>" + money(r.latest_sales) + "</td>" +
                    "<td>" + money(r.projected_monthly) + "</td>" +
                    "<td>" + money(r.projected_annual) + "</td>" +
                    "</tr>"
                )).join("");

                document.querySelectorAll("#pace-table th").forEach(th => {{
                    const arrow = th.querySelector(".arrow");
                    if (th.dataset.key === sortKey) {{
                        arrow.textContent = sortAsc ? "▲" : "▼";
                    }} else {{
                        arrow.textContent = "";
                    }}
                }});
            }}

            function sortRows(key, type) {{
                if (sortKey === key) {{
                    sortAsc = !sortAsc;
                }} else {{
                    sortKey = key;
                    sortAsc = true;
                }}
                rows.sort((a, b) => {{
                    let av = a[key], bv = b[key];
                    let cmp = type === "number" ? (av - bv) : String(av).localeCompare(String(bv));
                    return sortAsc ? cmp : -cmp;
                }});
                render();
            }}

            document.querySelectorAll("#pace-table th").forEach(th => {{
                th.addEventListener("click", () => sortRows(th.dataset.key, th.dataset.type));
            }});

            render();
        </script>
        """,
        height=table_height,
    )

    # Regional groupings, matched by store name (not store_key, since key
    # numbering doesn't reflect any north/south grouping). Note: the config
    # names this store "Greenville" (not "Lower Greenville") - matched
    # accordingly below.
    NORTH_STORES = {"Aubrey", "Rowlett", "Princeton", "Frisco", "Liquor Depot"}
    SOUTH_STORES = {"Oak Lawn", "Greenville", "West Greenville", "Lovers", "Hillcrest"}

    pace_by_name = {row["store"]: row["projected_monthly"] for row in rows}

    north_total = sum(pace_by_name.get(name, 0.0) for name in NORTH_STORES)
    south_total = sum(pace_by_name.get(name, 0.0) for name in SOUTH_STORES)

    north_missing = sorted(NORTH_STORES - pace_by_name.keys())
    south_missing = sorted(SOUTH_STORES - pace_by_name.keys())

    st.markdown(
        "<hr style='margin: 4px 0 0 0; border-color: #333;'>",
        unsafe_allow_html=True,
    )

    # Default st.columns gap is ~24px and st.metric's value font-size is
    # ~2.25rem - built with custom HTML instead of st.metric so the gap
    # (-75% -> 6px) and value font size (-50% -> 1.125rem) can be set
    # precisely rather than snapping to Streamlit's small/medium/large steps.
    def _region_block(label, total, missing):
        missing_html = (
            f"<div class='region-missing'>Not found: {', '.join(missing)}</div>"
            if missing else ""
        )
        return f"""
        <div class="region-block">
            <div class="region-label">{label}</div>
            <div class="region-value">${total:,.2f}</div>
            {missing_html}
        </div>
        """

    st.markdown(
        f"""
        <style>
        .region-row {{
            display: flex;
            gap: 6px;
            margin-top: -12px;
        }}
        .region-block {{
            flex: 0 0 auto;
        }}
        .region-label {{
            font-size: 0.875rem;
            opacity: 0.7;
        }}
        .region-value {{
            font-size: 1.125rem;
            font-weight: 600;
        }}
        .region-missing {{
            font-size: 0.75rem;
            opacity: 0.6;
        }}
        </style>
        <div class="region-row">
            {_region_block("North Stores Pace", north_total, north_missing)}
            {_region_block("South Stores Pace", south_total, south_missing)}
        </div>
        """,
        unsafe_allow_html=True,
    )
