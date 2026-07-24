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
"""
import pandas as pd
import streamlit as st

from lightspeed_client import load_config
from sales_pace import compute_pace, read_daily_log, update_daily_log

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
            "Store": store_names[store_key],
            "As Of": f"{as_of.month}/{as_of.day}" if as_of else "-",
            "Latest Day's Sales": pace["yesterday_total"],
            "Projected Monthly Total": pace["projected_monthly"],
            "Projected Annual Total": pace["projected_annual"],
        })

    rows.sort(key=lambda row: row["Store"])

    def _money(value):
        return f"${value:,.2f}"

    def _row_html(row):
        latest_sales = row["Latest Day's Sales"]
        return (
            "<tr>"
            f"<td class='store-cell'>{row['Store']}</td>"
            f"<td>{row['As Of']}</td>"
            f"<td>{_money(latest_sales)}</td>"
            f"<td>{_money(row['Projected Monthly Total'])}</td>"
            f"<td>{_money(row['Projected Annual Total'])}</td>"
            "</tr>"
        )

    table_rows = "".join(_row_html(row) for row in rows)

    st.markdown(
        f"""
        <style>
        .pace-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .pace-table th {{
            font-weight: 700;
            text-align: left;
            padding: 8px 12px;
            border-bottom: 2px solid #444;
        }}
        .pace-table td {{
            padding: 8px 12px;
            border-bottom: 1px solid #333;
        }}
        .pace-table td.store-cell {{
            font-weight: 700;
        }}
        </style>
        <table class="pace-table">
            <tr>
                <th>Store</th>
                <th>As Of</th>
                <th>Latest Day's Sales</th>
                <th>Projected Monthly Total</th>
                <th>Projected Annual Total</th>
            </tr>
            {table_rows}
        </table>
        """,
        unsafe_allow_html=True,
    )
