import streamlit as st
import pandas as pd
from optimiser import simulate
import openai, os

openai.api_key = st.secrets["OPENAI_API_KEY"]        #  ⬅️ new


# optional GPT explanation (works only if OPENAI_API_KEY is set in secrets)
try:
    from openai import OpenAI
    client = OpenAI()
    USE_GPT = True
except Exception:
    USE_GPT = False

# ---------- Streamlit page config -------------
st.set_page_config(page_title="A/R Simplex Optimiser", layout="centered")
st.title("Accounts-Receivable Simplex Optimiser 🚀")

# ---------- Upload / sample data --------------
sample = pd.DataFrame({
    "bucket": ["current","1_30","31_60","61_90","91_120","120_plus"],
    "balance":[8985917.53,600000.00,443229.09,158527.74,43891.93,368433.71]
})
uploaded = st.file_uploader("Upload ageing CSV", type=["csv"])
data = pd.read_csv(uploaded) if uploaded else sample
st.dataframe(data, hide_index=True)

# ---------- KPI sliders -----------------------
tgt_csr = st.slider("Target Current %", 90.0, 100.0, 96.5) / 100
max_pdr = st.slider("Max 120+ %", 0.0, 10.0, 2.0) / 100
horizon = st.selectbox("Projection horizon (months)", [1, 3, 6, 12])

# ---------- Optimise button -------------------
if st.button("Optimise"):
    bal_dict = dict(zip(data.bucket, data.balance))
    history = simulate(
        bal_dict, horizon,
        target_current=tgt_csr,
        max_120p_ratio=max_pdr,
    )
    rec = history[0]["recoveries"]
    last = history[-1]["kpi"]

    # display results
    st.subheader("Month-1 liquidation targets (%)")
    st.json(rec)

    st.subheader(f"KPI projection after {horizon} months")
    col1, col2 = st.columns(2)
    col1.metric("Current ratio", f"{last['current_ratio']:.2%}")
    col2.metric("120+ ratio", f"{last['pdr_ratio']:.2%}")

    # optional GPT explanation
    if USE_GPT:
        with st.spinner("Generating AI explanation…"):
            prompt = f"""Explain (≤180 words, clear English) why the optimiser
            suggests these Month-1 recoveries {rec} and what the portfolio will
            look like after {horizon} months (CSR {last['current_ratio']:.2%},
            PDR {last['pdr_ratio']:.2%})."""
            try:
                gpt = client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.4,
                    messages=[{"role": "user", "content": prompt}]
                )
                explanation = gpt.choices[0].message.content.strip()
            except Exception as e:
                explanation = f"(GPT error – {e})"
        st.subheader("AI rationale")
        st.text_area("", explanation, height=180)

