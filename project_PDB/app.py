
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.express as px
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="World GDP Heatmap", layout="wide")

START_YEAR = 2010
END_YEAR = 2028
OUT_DIR = Path("outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

@st.cache_data(ttl=24*3600)
def fetch_countries() -> pd.DataFrame:
    rows, page = [], 1
    while True:
        url = f\"https://api.worldbank.org/v2/country?format=json&per_page=300&page={page}\"
        res = requests.get(url, timeout=120)
        res.raise_for_status()
        j = res.json()
        if page == 1:
            total = j[0].get("total", 0)
        rows += j[1]
        if len(rows) >= total:
            break
        page += 1
    df = pd.DataFrame([{
        "name": r["name"],
        "iso3": r["id"],
        "region_id": r["region"]["id"],
        "region": r["region"]["value"],
        "income": r["incomeLevel"]["value"]
    } for r in rows])
    return df[df["region_id"] != "NA"].reset_index(drop=True)

@st.cache_data(ttl=24*3600)
def fetch_indicator_latest(indicator: str, start_year: int, end_year: int) -> pd.DataFrame:
    rows, page = [], 1
    while True:
        url = (f\"https://api.worldbank.org/v2/country/all/indicator/{indicator}\"
               f\"?format=json&per_page=20000&date={start_year}:{end_year}&page={page}\")
        res = requests.get(url, timeout=180)
        res.raise_for_status()
        j = res.json()
        if not isinstance(j, list) or len(j) < 2:
            break
        if page == 1:
            total = j[0].get("total", 0)
        rows += j[1]
        if len(rows) >= total:
            break
        page += 1

    df = pd.DataFrame([{
        "iso3": r.get("countryiso3code"),
        "year": int(r.get("date")) if r.get("date") else None,
        "value": r.get("value")
    } for r in rows if r and r.get("countryiso3code")])
    df = (df.sort_values(["iso3","year"], ascending=[True, False])
            .dropna(subset=["value"])
            .groupby("iso3", as_index=False).first())
    return df

def build_dataset(indicator: str) -> pd.DataFrame:
    c = fetch_countries()
    v = fetch_indicator_latest(indicator, START_YEAR, END_YEAR)
    return c.merge(v, on="iso3", how="left")

st.title("🌍 World GDP Heatmap")
st.caption("World Bank — latest available per country")

with st.sidebar:
    st.header("Controls")
    indicator_label = st.selectbox(
        "Indicator",
        ["NY.GDP.MKTP.CD — GDP (current US$)",
         "NY.GDP.PCAP.CD — GDP per capita (current US$)"],
        index=0
    )
    USE_LOG = st.checkbox("Log scale (recommended)", True)

    df_cty = fetch_countries()
    regions = ["All"] + sorted(df_cty["region"].dropna().unique().tolist())
    region_pick = st.selectbox("Region filter", regions, index=0)

    incomes = ["All"] + sorted(df_cty["income"].dropna().unique().tolist())
    income_pick = st.selectbox("Income level filter", incomes, index=0)

    if st.button("🔄 Refresh cache"):
        fetch_countries.clear()
        fetch_indicator_latest.clear()
        st.success("Cache cleared. Data will refresh on next run.")

indicator = "NY.GDP.MKTP.CD" if indicator_label.startswith("NY.GDP.MKTP.CD") else "NY.GDP.PCAP.CD"

with st.spinner("Fetching data from World Bank..."):
    df = build_dataset(indicator)

if region_pick != "All":
    df = df[df["region"] == region_pick]
if income_pick != "All":
    df = df[df["income"] == income_pick]

plot_df = df.copy()
if USE_LOG:
    plot_df["value_log10"] = plot_df["value"].apply(lambda x: np.log10(x) if pd.notna(x) and x > 0 else None)
    color_col = "value_log10"
    color_title = "log10(Value)"
else:
    color_col = "value"
    color_title = "Value"

fig = px.choropleth(
    plot_df,
    locations="iso3",
    color=color_col,
    hover_name="name",
    hover_data={"iso3": True, "year": True, "value": ":,.0f", color_col: False},
    color_continuous_scale="Viridis",
    projection="natural earth",
    title=f"{indicator} — latest available"
)
st.plotly_chart(fig, use_container_width=True)

OUT_DIR.mkdir(exist_ok=True, parents=True)
csv_path = OUT_DIR / "gdp_latest_by_country.csv"
html_path = OUT_DIR / "heatmap_gdp_world.html"

df.to_csv(csv_path, index=False)
fig.write_html(str(html_path), include_plotlyjs="cdn")

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "⬇️ Download CSV",
        data=csv_path.read_bytes(),
        file_name="gdp_latest_by_country.csv",
        mime="text/csv"
    )
with col2:
    st.download_button(
        "⬇️ Download HTML",
        data=html_path.read_bytes(),
        file_name="heatmap_gdp_world.html",
        mime="text/html"
    )

st.caption(f"Last run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
