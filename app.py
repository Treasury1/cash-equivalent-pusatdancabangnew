import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.markdown("""
<style>
p, div, h2, h3, h4, h5, h6, span {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  line-height: 1.2 !important;
}
h1 {
  margin-top: 0rem !important;
  margin-bottom: 0rem !important;
  font-size: 2rem !important;
}
.footer {
  text-align: center;
  font-size: 14px;
  margin-top: 0.3rem;
  color: #555;
}
body, .main { padding-top: 0.3rem !important; padding-bottom: 0.3rem !important; padding-left: 0.3rem !important; padding-right: 0.3rem !important; }
.block-container { padding-top: 1rem !important; padding-bottom: 0.2rem !important; padding-left: 1rem !important ;padding-right: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# --- LOAD DATA ---
sheet_id = "1vTzm9o_m2wwiiS4jWPbP-nMmelIwJCSonBx-pmiN2Q0"
url_saldo = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=SALDO"
url_cf = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=CASHFLOW"

df_saldo = pd.read_csv(url_saldo)
df_cf = pd.read_csv(url_cf)

# --- PREPARE SALDO DATA ---
df_saldo['TANGGAL'] = pd.to_datetime(df_saldo['TANGGAL'], dayfirst=True, errors='coerce')
latest_date = df_saldo['TANGGAL'].max()
saldo_latest = df_saldo[df_saldo['TANGGAL'] == latest_date].copy()
saldo_latest['JENIS SALDO'] = saldo_latest['JENIS SALDO'].astype(str).str.upper().str.strip()
saldo_latest['BANK'] = saldo_latest['BANK'].astype(str).str.upper().str.strip()

# Tampilkan info update setelah latest_date tersedia
update_info = latest_date.strftime("%d %B %Y")
bank_color_map = {
    'BRI': '#0A3185',
    'BSI': '#00A39D',
    'BTN': '#0057B8',
    'BNI': '#F37021',
    'MANDIRI': '#002F6C',
    'CIMB': '#990000',
    'BJB': '#AB9B56',
    'BCA': '#00529B',
    'RAYA': '#00549A',
    'BTN SYARIAH': '#FFC20E',
    'BRI USD': '#0A3185'
}
fallback_colors = ['#999999', '#BBBBBB', '#CCCCCC']

def get_bank_colors(banks: list[str]) -> list[str]:
    return [bank_color_map.get(bank.upper(), fallback_colors[i % len(fallback_colors)]) for i, bank in enumerate(banks)]

col1, col2 = st.columns([1, 6])  # Rasio lebar kolom logo dan judul
with col1:
    st.image("asdp-logo.png", width=80)  # Pastikan logo berada di root folder repo

with col2:
    st.markdown(
        "<h1 style='text-align:center; margin-bottom:0;'>Cash and Cash Equivalents Ending Balance Dashboard</h1>",
        unsafe_allow_html=True
    )
st.markdown(
    f"<p style='text-align:left; font-size:14px; margin-top:0.2rem;'><i>Data per {update_info}</i></p>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:left; font-size:13px; margin-top:-0.3rem;'><i>(Dalam Miliar Rupiah)</i></p>",
    unsafe_allow_html=True
)

# Warna khusus
custom_colors = px.colors.qualitative.Dark2

# Pivot tabel
pivot = saldo_latest.pivot_table(
    index='BANK',
    columns='JENIS SALDO',
    values='SALDO',
    aggfunc='sum',
    fill_value=0
).reset_index()

pivot['TOTAL SALDO'] = pivot.get('GIRO', 0) + pivot.get('DEPOSITO', 0)
pivot = pivot.sort_values(by='TOTAL SALDO', ascending=False).reset_index(drop=True)

# Format Grand Total
grand_total = pd.DataFrame({
    'BANK': ['GRAND TOTAL'],
    'GIRO': [pivot['GIRO'].sum()],
    'DEPOSITO': [pivot['DEPOSITO'].sum()],
    'TOTAL SALDO': [pivot['TOTAL SALDO'].sum()]
})
pivot_display = pd.concat([pivot, grand_total], ignore_index=True)
pivot_display[['GIRO', 'DEPOSITO', 'TOTAL SALDO']] = pivot_display[['GIRO', 'DEPOSITO', 'TOTAL SALDO']].round(0).astype(int)

# --- LAYOUT ---
col1, col2, col3 = st.columns([1.2, 1.2, 1.6])

with col1:

    st.markdown("#### Saldo per Bank")
    def highlight_grand_total(row):
        style = 'font-weight: bold; background-color: #f0f0f0' if row.name == len(pivot_display) - 1 else ''
        return [style] * len(row)
    styled_table = pivot_display.style.format(lambda x: '{:,.0f}'.format(x).replace(',', '.'), subset=['GIRO', 'DEPOSITO', 'TOTAL SALDO'])
    styled_table = styled_table.apply(highlight_grand_total, axis=1)

    st.dataframe(styled_table, use_container_width=True, hide_index=True, height=490)

    st.markdown("#### Restricted Cash and Cash Equivalents")
    saldo_latest['KETERANGAN'] = saldo_latest['KETERANGAN'].astype(str).str.upper().str.strip()
    summary = saldo_latest.groupby(['JENIS SALDO', 'KETERANGAN'])['SALDO'].sum().unstack(fill_value=0)
    summary['TOTAL'] = summary.sum(axis=1)
    summary = summary[['RESTRICTED', 'NON RESTRICTED', 'TOTAL']]
    summary_formatted = summary.apply(lambda col: col.map(fmt_number))
    st.dataframe(summary_formatted, use_container_width=True, height=105)

with col2:
    st.markdown("### Persentase GIRO per Bank")
    giro_data = pivot[pivot['GIRO'] > 0]
    giro_colors = get_bank_colors(giro_data['BANK'].tolist())
    fig_giro = px.pie(giro_data, names='BANK', values='GIRO', hole=0.4)
    fig_giro.update_traces(marker=dict(colors=giro_colors), textinfo='percent+label')
    fig_giro.update_layout(showlegend=False)
    st.plotly_chart(fig_giro, use_container_width=True, config={"displayModeBar": False})

    st.markdown("### Persentase DEPOSITO per Bank")
    deposito_data = saldo_latest[saldo_latest['JENIS SALDO'] == 'DEPOSITO']
    min_rate = deposito_data['RATE (%)'].min()
    max_rate = deposito_data['RATE (%)'].max()
    rate_range = st.slider("Filter berdasarkan Rate (%)", float(min_rate), float(max_rate), (float(min_rate), float(max_rate)))
    deposito_filtered = deposito_data[deposito_data['RATE (%)'].between(rate_range[0], rate_range[1])]
    deposito_grouped = deposito_filtered.groupby('BANK')['SALDO'].sum().reset_index()
    depo_colors = get_bank_colors(deposito_grouped['BANK'].tolist())
    fig_depo = px.pie(deposito_grouped, names='BANK', values='SALDO', hole=0.4)
    fig_depo.update_traces(marker=dict(colors=depo_colors), textinfo='percent+label')
    fig_depo.update_layout(showlegend=False)
    st.plotly_chart(fig_depo, use_container_width=True, config={"displayModeBar": False})

with col3:
    st.markdown("### Grafik Tren Cash and Cash Equivalents (12 Bulan Terakhir)")
    df_saldo['BULAN'] = df_saldo['TANGGAL'].dt.to_period('M').dt.to_timestamp()
    pivot_trend = df_saldo.copy()
    pivot_trend['JENIS SALDO'] = pivot_trend['JENIS SALDO'].astype(str).str.upper().str.strip()
    monthly = pivot_trend.groupby(['BULAN', 'JENIS SALDO'])['SALDO'].sum().unstack(fill_value=0)
    monthly['TOTAL'] = monthly.sum(axis=1)
    last_12 = monthly.tail(12).reset_index()
    last_12['BULAN_LABEL'] = last_12['BULAN'].dt.strftime('%b %Y')
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=last_12['BULAN_LABEL'], y=last_12['TOTAL'], mode='lines+markers+text',
                                  name='TOTAL SALDO', text=last_12['TOTAL'].apply(lambda x: '{:,.0f}'.format(x).replace(',', '.')),
                                  textposition='top center', line=dict(color=custom_colors[0])))
    fig_line.update_layout(yaxis_title="Saldo", xaxis_title="BULAN")
    st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})

    st.markdown("### Grafik CASH IN / OUT (12 Bulan Terakhir)")
    df_cf['TANGGAL'] = pd.to_datetime(df_cf['TANGGAL'], dayfirst=True, errors='coerce')
    df_cf['BULAN'] = df_cf['TANGGAL'].dt.to_period('M').dt.to_timestamp()
    cash_pivot = df_cf.groupby('BULAN')[['CASH IN', 'CASH OUT', 'NET']].sum().tail(12).reset_index()
    cash_pivot['BULAN_LABEL'] = cash_pivot['BULAN'].dt.strftime('%b %Y')
    fig_combo = go.Figure()
    fig_combo.add_trace(go.Bar(x=cash_pivot['BULAN_LABEL'], y=cash_pivot['CASH IN'], name='CASH IN', marker_color=custom_colors[1]))
    fig_combo.add_trace(go.Bar(x=cash_pivot['BULAN_LABEL'], y=cash_pivot['CASH OUT'], name='CASH OUT', marker_color=custom_colors[2]))
    fig_combo.add_trace(go.Scatter(x=cash_pivot['BULAN_LABEL'], y=cash_pivot['NET'],
                                   name='NET', mode='lines+markers+text',
                                   text=cash_pivot['NET'].round(0).astype(int),
                                   textposition='top center', line=dict(color='black'), textfont=dict(color='black')))
    fig_combo.update_layout(barmode='group', xaxis_title="BULAN", yaxis_title="Cash in/Out")
    st.plotly_chart(fig_combo, use_container_width=True, config={"displayModeBar": False})

# --- FOOTER ---
st.markdown("""<div class="footer">Created by Nur Vita Anjaningrum</div>""", unsafe_allow_html=True)
