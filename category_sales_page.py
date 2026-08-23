"""
Category Sales page (category_sales_page.py).

Lets the user pick a category (e.g. "Rolling Trays"), a date range, and
which stores to include, then shows how much each selected store sold in
that category over that period.

NOTE: Categories are per-account in Lightspeed, so the same category name
can have a different categoryID at each store. This page builds the
dropdown from category *names* merged across all stores, then resolves the
right categoryID for each store individually before pulling sales. Stores
are queried in parallel (each store is an independent Lightspeed account,
so there's no shared state to worry about).
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def run_report(store_keys, categories_by_store, selected_category, start_date, end_date):
    """Fetches category sales for each store in parallel."""
    config = ls.load_config()
    results = {}

    def _fetch_one(store_key):
        store_categories = categories_by_store[store_key]
        category_id = next(
            (cid for cid, name in store_categories.items() if name == selected_category),
            None,
        )
        if category_id is None:
            return store_key, None  # no match at this store
        return store_key, ls.fetch_category_sales(
            config, store_key, category_id, start_date, end_date
        )

    with ThreadPoolExecutor(max_workers=max(len(store_keys), 1)) as pool:
        futures = [pool.submit(_fetch_one, store_key) for store_key in store_keys]
        for future in as_completed(futures):
            store_key, result = future.result()
            results[store_key] = result

    return results


config = ls.load_config()
all_store_keys = list(config["stores"].keys())

with st.spinner("Loading categories..."):
    categories_by_store = get_categories_by_store(tuple(all_store_keys))

category_options = build_name_options(categories_by_store)

if not category_options:
    st.warning("No categories found. Check that stores_config.json / STORES_CONFIG_JSON is set up correctly.")
    st.stop()

selected_category = st.selectbox("Category", category_options)

store_scope = st.radio("Stores", ["All stores", "Choose stores"], horizontal=True)
if store_scope == "All stores":
    selected_stores = all_store_keys
else:
    selected_stores = st.multiselect("Select stores", all_store_keys, default=all_store_keys)

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start date", value=date.today() - timedelta(days=30))
with col2:
    end_date = st.date_input("End date", value=date.today())

if start_date > end_date:
    st.error("Start date must be before end date.")
    st.stop()

if not selected_stores:
    st.info("Pick at least one store to run the report.")
    st.stop()

if st.button("Run report", type="primary"):
    with st.spinner(f"Fetching sales for {len(selected_stores)} store(s)..."):
        results = run_report(
            selected_stores, categories_by_store, selected_category, start_date, end_date
        )

    rows = []
    missing_stores = []
    for store_key in selected_stores:
        result = results.get(store_key)
        if result is None:
            missing_stores.append(store_key)
            rows.append({"Store": store_key, "Total Sales": 0.0, "Units Sold": 0.0})
        else:
            rows.append({
                "Store": store_key,
                "Total Sales": result["total"],
                "Units Sold": result["quantity"],
            })

    if missing_stores:
        st.warning(
            f"No category named \"{selected_category}\" found at: "
            f"{', '.join(missing_stores)}. Shown as $0 below - this likely "
            f"means that store uses a slightly different category name."
        )

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
