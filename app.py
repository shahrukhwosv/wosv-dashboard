"""
App entry point / router.

This file's ONLY job is to set up the page and switch between the two
tools using Streamlit's navigation API, which lets us control the exact
sidebar labels ("Commissions" / "Transactions") instead of Streamlit's
default file-name-based labels.

Run with:  streamlit run app.py   (same as always - nothing changes for
local use or for Railway's start command).

The actual page content lives in commission_page.py and
reconciliation_page.py.
"""

import streamlit as st

st.set_page_config(page_title="WOSV Dashboard", layout="wide")

commissions_page = st.Page(
    "commission_page.py", title="Commissions", icon="💰"
)
transactions_page = st.Page(
    "reconciliation_page.py", title="Transactions", icon="💳"
)

pg = st.navigation([commissions_page, transactions_page])
pg.run()
