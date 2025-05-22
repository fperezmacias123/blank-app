import streamlit as st
import pandas as pd
from optimiser import simulate          # we’ll add optimiser.py next
import openai, os

openai.api_key = st.secrets["OPENAI_API_KEY"]        #  ⬅️ new


st.set_page_config(page_title="A/R Simplex Optimiser", layout="centered")

st.title("Accounts-Receivable Simplex Optimiser  🚀")

# ---------- file upload ----------------------------------------------------
sample = pd.DataFrame({
    "bucket": ["current","31_60","61_90","91_120","120_plus"],
    "balance":[8985917.53,443229.09,158527.74,43891.93,368433.71]
})
uploaded = st.file_uploader("Upload ageing CSV", type=["csv"])
data = pd.read_csv(uploaded) if uploaded else sample
st.dataframe(data, hide_index=True)

# ---------- KPI targets ----------------------------------------------------
tgt_csr = st.slider("Target *Current* %", 90.0, 100.0, 96.5) / 100
max_pdr = st.slider("Max *120 +* %", 0.0, 10.0, 2.0) / 100
horizon = st.selectbox("Projection horizon (months)", [1, 3, 6, 12])

# ---------- run optimiser --------------------------------------------------
if st.button("Optimise"):
    balances = dict(zip(data.bucket, data.balance))
    history = simulate(balances, horizon,
                       target_current=tgt_csr,
                       max_120p_ratio=max_pdr)
    rec = history[0]["recoveries"]
    last = history[-1]["kpi"]

    st.subheader("First-month liquidation targets (%)")
    st.json(rec)

    st.subheader(f"KPI projection after {horizon} m")
    col1, col2 = st.columns(2)
    col1.metric("Current-status ratio", f"{last['current_ratio']:.2%}")
    col2.metric("120 + ratio", f"{last['pdr_ratio']:.2%}")
