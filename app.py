import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

st.set_page_config(layout="wide")

# =========================
# FORMAT ANGKA (AMAN)
# =========================
def fmt_number(x):
    try:
        if pd.isna(x):
            return "-"
        return "{:,.0f}".format(x).replace(",", ".")
    except:
        return x

# =========================
# STYLE
# =========================
st.markdown("""
<style>
h1 {text-align:center;}
.footer {text-align:center; font-size:14px; color:#555;}
</style>
""", unsafe_allow_html=True)

# =========================
# LOAD DATA (AMAN)
# =========================
sheet_id = "1vTzm9o_m2wwiiS4jWPbP-nMmelIwJCSonBx-pmiN2Q0"

def load_data(sheet_name):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        return pd.read_csv(url)
    except:
        return pd.DataFrame()

df_saldo = load_data("SALDO")
df_cf = load_data("CASHFLOW")

if df_saldo.empty:
    st.error("Data SALDO tidak ditemukan")
    st.stop()

# =========================
# PREPROCESS
# =========================
df_saldo['TANGGAL'] = pd.to_datetime(df_saldo['TANGGAL'], errors='coerce')
latest_date = df_saldo['TANGGAL'].max()

saldo_latest = df_saldo[df_saldo['TANGGAL'] == latest_date].copy()

for col in ['BANK', 'JENIS SALDO', 'KETERANGAN']:
    if col in saldo_latest.columns:
        saldo_latest[col] = saldo_latest[col].astype(str).str.upper().str.strip()

# =========================
# HEADER
# =========================
col1, col2 = st.columns([1,6])

with col1:
    logo_path = os.path.join(os.path.dirname(__file__), "asdp-logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=80)

with col2:
    st.markdown("<h1>Cash and Cash Equivalents Dashboard</h1>", unsafe_allow_html=True)

st.markdown(f"**Data per: {latest_date.strftime('%d %B %Y')}**")

# =========================
# PIVOT TABLE
# =========================
pivot = saldo_latest.pivot_table(
    index='BANK',
    columns='JENIS SALDO',
    values='SALDO',
    aggfunc='sum',
    fill_value=0
).reset_index()

pivot['TOTAL'] = pivot.get('GIRO',0) + pivot.get('DEPOSITO',0)
pivot = pivot.sort_values(by='TOTAL', ascending=False)

# =========================
# LAYOUT
# =========================
col1, col2, col3 = st.columns([1.2,1.2,1.6])

# =========================
# TABLE SALDO
# =========================
with col1:
    st.subheader("Saldo per Bank")

    pivot_display = pivot.copy()
    for col in ['GIRO','DEPOSITO','TOTAL']:
        if col in pivot_display.columns:
            pivot_display[col] = pivot_display[col].apply(fmt_number)

    st.dataframe(pivot_display, use_container_width=True, hide_index=True)

# =========================
# SUMMARY (ANTI ERROR)
# =========================
    st.subheader("Restricted vs Non Restricted")

    if not saldo_latest.empty:
        summary = saldo_latest.groupby(['JENIS SALDO','KETERANGAN'])['SALDO'].sum()

        if isinstance(summary, pd.Series):
            summary = summary.unstack(fill_value=0)

        if summary.empty:
            summary = pd.DataFrame({'RESTRICTED':[0],'NON RESTRICTED':[0]})

        summary['TOTAL'] = summary.sum(axis=1)

        for col in ['RESTRICTED','NON RESTRICTED']:
            if col not in summary.columns:
                summary[col] = 0

        summary = summary[['RESTRICTED','NON RESTRICTED','TOTAL']]

        for col in summary.columns:
            summary[col] = summary[col].apply(fmt_number)

        st.dataframe(summary, use_container_width=True)

# =========================
# PIE CHART
# =========================
with col2:
    st.subheader("Persentase Giro")

    if 'GIRO' in pivot.columns:
        fig = px.pie(pivot, names='BANK', values='GIRO', hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

# =========================
# TREND
# =========================
with col3:
    st.subheader("Trend Saldo")

    df_saldo['BULAN'] = df_saldo['TANGGAL'].dt.to_period('M').dt.to_timestamp()
    trend = df_saldo.groupby('BULAN')['SALDO'].sum().reset_index().tail(12)

    fig = px.line(trend, x='BULAN', y='SALDO')
    st.plotly_chart(fig, use_container_width=True)

# =========================
# FOOTER
# =========================
st.markdown("<div class='footer'>Created by Nur Vita Anjaningrum</div>", unsafe_allow_html=True)
