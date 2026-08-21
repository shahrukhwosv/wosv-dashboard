"""
Category Sales page.

Lets the user pick a category (e.g. "Rolling Trays") from a dropdown and a
date range, then shows how much each store sold in that category over that
period.

NOTE: Categories are per-account in Lightspeed, so the same category name
can have a different categoryID at each store. This page builds the
dropdown from category *names* merged across all stores, then resolves the
right categoryID for each store individually before pulling sales.
"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import lightspeed_client as ls

st.title("Category Sales")


@st.cache_data(ttl=3600, show_spinner=False)
def get_categories_by_store(store_keys):
    """Returns {store_key: {categoryID: name}} for every store."""
    config = ls.load_config()
    return {
        store_key: ls.fetch_categories(config, store_key)
        for store_key in store_keys
    }


def build_name_options(categories_by_store):
    """Merges categories from every store into a sorted list of unique names."""
    names = set()
    for categories in categories_by_store.values():
        names.update(categories.values())
    return sorted(names, key=str.casefold)


config = ls.load_config()
store_keys = list(config["stores"].keys())

with st.spinner("Loading categories..."):
    categories_by_store = get_categories_by_store(tuple(store_keys))

category_options = build_name_options(categories_by_store)

if not category_options:
    st.warning("No categories found. Check that stores_config.json / STORES_CONFIG_JSON is set up correctly.")
    st.stop()

selected_category = st.selectbox("Category", category_options)

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=date.today() - timedelta(days=30))
with col2:
    end_date = st.date_input("End date", value=date.today())

if start_date > end_date:
    st.error("Start date must be before end date.")
    st.stop()

if st.button("Run report", type="primary"):
    rows = []
    progress = st.progress(0.0, text="Fetching sales...")

    for i, store_key in enumerate(store_keys):
        store_categories = categories_by_store[store_key]
        # Find this store's categoryID for the selected name.
        category_id = next(
            (cid for cid, name in store_categories.items() if name == selected_category),
            None,
        )

        if category_id is None:
            rows.append({"Store": store_key, "Total Sales": 0.0, "Units Sold": 0.0})
        else:
            progress.progress(i / len(store_keys), text=f"Fetching sales for {store_key}...")
            result = ls.fetch_category_sales(config, store_key, category_id, start_date, end_date)
            rows.append({
                "Store": store_key,
                "Total Sales": result["total"],
                "Units Sold": result["quantity"],
            })

    progress.empty()

    df = pd.DataFrame(rows)
    total_row = pd.DataFrame([{
        "Store": "TOTAL",
        "Total Sales": df["Total Sales"].sum(),
        "Units Sold": df["Units Sold"].sum(),
    }])
    df = pd.concat([df, total_row], ignore_index=True)

    st.dataframe(
        df,
        column_config={
            "Total Sales": st.column_config.NumberColumn(format="$%.2f"),
            "Units Sold": st.column_config.NumberColumn(format="%.0f"),
        },
        hide_index=True,
        use_container_width=True,
    )
