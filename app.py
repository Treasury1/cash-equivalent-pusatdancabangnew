from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import json
import math
import os

import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials


# =========================================================
# KONSTANTA
# =========================================================
SHEET_GIRO_DEPOSITO = "giro deposito"
SHEET_TOTAL = "total"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


# =========================================================
# STRUKTUR KOLOM
# =========================================================
@dataclass(frozen=True)
class ColGD:
    tanggal: str = "TANGGAL"
    bank: str = "BANK"
    tipe: str = "TYPE"
    cabang_pusat: str = "CABANG/PUSAT"
    keterangan: str = "KETERANGAN"
    saldo: str = "SALDO AKHIR"


@dataclass(frozen=True)
class ColTotal:
    tahun: str = "TAHUN"
    total: str = "CASH & CASH EQUIVALENTS"


# =========================================================
# STYLE
# =========================================================
def inject_css():
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 1.2rem !important;
                max-width: 1400px;
            }
            h1 {
                text-align: center;
                font-size: 1.7rem !important;
                margin-bottom: 0.6rem;
            }
            .update-info {
                text-align: left;
                font-style: italic;
                margin-top: -0.2rem;
                margin-bottom: 1rem;
                color: #555;
            }
            .footer-credit {
                text-align: center;
                font-size: 0.85rem;
                color: #666;
                font-style: italic;
                margin-top: 1.5rem;
                padding-bottom: 0.5rem;
            }
            table {
                width: 100%;
                border-collapse: collapse;
            }
            table th {
                text-align: center !important;
                font-weight: 700 !important;
                background-color: #f8f9fa !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# UTILITAS
# =========================================================
def round_half_up(n):
    if pd.isna(n):
        return 0
    return int(math.floor(float(n) + 0.5))


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


def normalize_service_account(info: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(info)
    if "private_key" in data and isinstance(data["private_key"], str):
        data["private_key"] = data["private_key"].replace("\\n", "\n")
    return data


def make_html_table(df: pd.DataFrame, label_col: str) -> str:
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    html = "<table style='width:100%; border-collapse:collapse;'>"
    html += "<thead><tr>"
    for col in df.columns:
        html += (
            "<th style='border:1px solid #ddd; padding:6px; "
            "background:#f8f9fa; text-align:center;'>"
            f"{col}</th>"
        )
    html += "</tr></thead><tbody>"

    for _, row in df.iterrows():
        is_grand_total = str(row[label_col]) == "Grand Total"
        row_style = "background:#f2f2f2; font-weight:700;" if is_grand_total else ""
        html += f"<tr style='{row_style}'>"

        for col in df.columns:
            val = row[col]
            align = "left" if col == label_col else "right"

            if col in numeric_cols:
                try:
                    val = f"{float(val):,.0f}"
                except Exception:
                    pass

            html += (
                f"<td style='border:1px solid #ddd; padding:6px; text-align:{align};'>"
                f"{val}</td>"
            )

        html += "</tr>"

    html += "</tbody></table>"
    return html


# =========================================================
# KONFIGURASI
# =========================================================
def show_setup_help():
    st.error("Konfigurasi Google Sheets / service account belum terbaca.")

    st.markdown(
        """
Isi **Streamlit Secrets** di Streamlit Cloud dengan format berikut.
Buka:

**App settings → Secrets**
"""
    )

    st.code(
        '''SPREADSHEET_ID = "ISI_SPREADSHEET_ID"

[gcp_service_account]
type = "service_account"
project_id = "xxxxx"
private_key_id = "xxxxx"
private_key = "-----BEGIN PRIVATE KEY-----\\nxxxxx\\n-----END PRIVATE KEY-----\\n"
client_email = "xxxxx@xxxxx.iam.gserviceaccount.com"
client_id = "xxxxx"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/xxxxx"
universe_domain = "googleapis.com"
''',
        language="toml",
    )

    st.warning(
        "Pastikan file Google Sheet Anda sudah di-share ke email service account "
        "(client_email) sebagai Viewer."
    )


def load_runtime_config() -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    spreadsheet_id = None
    service_account_info = None

    try:
        if "SPREADSHEET_ID" in st.secrets:
            spreadsheet_id = str(st.secrets["SPREADSHEET_ID"]).strip()

        if "gcp_service_account" in st.secrets:
            service_account_info = normalize_service_account(
                dict(st.secrets["gcp_service_account"])
            )
    except Exception:
        pass

    if not spreadsheet_id:
        spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip() or None

    if not service_account_info:
        raw = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "").strip()
        if raw:
            try:
                service_account_info = normalize_service_account(json.loads(raw))
            except json.JSONDecodeError:
                st.sidebar.error("GCP_SERVICE_ACCOUNT_JSON bukan JSON yang valid.")

    return spreadsheet_id, service_account_info


def require_config() -> Tuple[str, Dict[str, Any]]:
    spreadsheet_id, service_account_info = load_runtime_config()

    if not spreadsheet_id or not service_account_info:
        show_setup_help()
        st.stop()

    return spreadsheet_id, service_account_info


# =========================================================
# GOOGLE SHEETS
# =========================================================
@st.cache_resource(show_spinner=False)
def get_gspread_client(service_account_json: str) -> gspread.Client:
    info = json.loads(service_account_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=300, show_spinner=False)
def load_sheet(
    spreadsheet_id: str,
    worksheet_name: str,
    service_account_json: str,
) -> pd.DataFrame:
    gc = get_gspread_client(service_account_json)
    ws = gc.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)


# =========================================================
# VALIDASI
# =========================================================
def validate_columns(df: pd.DataFrame, required_cols: list[str], sheet_name: str):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Kolom pada sheet '{sheet_name}' tidak lengkap: {missing}")
        st.stop()


# =========================================================
# MAIN
# =========================================================
def main():
    st.set_page_config(
        page_title="Cash and Cash Equivalents Dashboard",
        layout="wide",
    )

    inject_css()

    st.markdown("<h1>Cash and Cash Equivalents Dashboard</h1>", unsafe_allow_html=True)

    spreadsheet_id, service_account_info = require_config()
    service_account_json = json.dumps(service_account_info, sort_keys=True)

    try:
        gd = load_sheet(spreadsheet_id, SHEET_GIRO_DEPOSITO, service_account_json)
        total = load_sheet(spreadsheet_id, SHEET_TOTAL, service_account_json)
    except Exception as e:
        st.error("Gagal membaca data dari Google Sheets.")
        st.info(
            "Cek 4 hal ini:\n"
            "1. SPREADSHEET_ID benar\n"
            "2. Nama worksheet benar\n"
            "3. Google Sheet sudah di-share ke service account\n"
            "4. Isi secrets valid"
        )
        st.exception(e)
        st.stop()

    if gd.empty:
        st.warning(f"Worksheet '{SHEET_GIRO_DEPOSITO}' kosong.")
        st.stop()

    if total.empty:
        st.warning(f"Worksheet '{SHEET_TOTAL}' kosong.")
        st.stop()

    cg = ColGD()
    ct = ColTotal()

    validate_columns(
        gd,
        [cg.tanggal, cg.bank, cg.tipe, cg.cabang_pusat, cg.keterangan, cg.saldo],
        SHEET_GIRO_DEPOSITO,
    )
    validate_columns(
        total,
        [ct.tahun, ct.total],
        SHEET_TOTAL,
    )

    # Normalisasi
    gd[cg.bank] = gd[cg.bank].astype(str).str.strip().str.upper()
    gd[cg.tipe] = gd[cg.tipe].astype(str).str.strip().str.upper()
    gd[cg.cabang_pusat] = gd[cg.cabang_pusat].astype(str).str.strip().str.upper()
    gd[cg.keterangan] = gd[cg.keterangan].fillna("").astype(str).str.strip().str.upper()
    gd[cg.saldo] = to_numeric(gd[cg.saldo]).fillna(0.0)

    total[ct.tahun] = total[ct.tahun].astype(str).str.strip()
    total[ct.total] = to_numeric(total[ct.total]).fillna(0.0)

    update_date = pd.to_datetime(gd[cg.tanggal], errors="coerce").max()
    update_text = update_date.strftime("%d %B %Y") if pd.notna(update_date) else "-"

    st.markdown(
        f"""
        <div class="update-info">
            Updated per {update_text}<br>
            (In Billion Rupiah)
        </div>
        """,
        unsafe_allow_html=True,
    )

    # =====================================================
    # PEMISAHAN DATA
    # =====================================================
    deposito_restricted = gd[
        (gd[cg.tipe] == "DEPOSITO")
        & (gd[cg.keterangan].str.contains(r"\bRESTRICT(ED)?\b", case=False, na=False))
        & (~gd[cg.keterangan].str.contains("NON", case=False, na=False))
    ]
    restricted_total = deposito_restricted[cg.saldo].sum()

    deposito_non = gd[
        (gd[cg.tipe] == "DEPOSITO")
        & (gd[cg.keterangan].str.contains("NON", case=False, na=False))
    ]

    giro = gd[gd[cg.tipe] == "GIRO"]
    kas = gd[gd[cg.tipe] == "KAS"]

    # =====================================================
    # TABEL TOTAL
    # =====================================================
    table_total = pd.DataFrame({"Cabang/Pusat": ["CABANG", "PUSAT"]})

    depo_non_sum = (
        deposito_non.groupby(cg.cabang_pusat, as_index=False)[cg.saldo]
        .sum()
        .rename(columns={cg.saldo: "Total Deposito (Non Restricted)"})
    )

    giro_sum = (
        giro.groupby(cg.cabang_pusat, as_index=False)[cg.saldo]
        .sum()
        .rename(columns={cg.saldo: "Total Giro"})
    )

    kas_sum = (
        kas.groupby(cg.cabang_pusat, as_index=False)[cg.saldo]
        .sum()
        .rename(columns={cg.saldo: "Total Kas"})
    )

    table_total = table_total.merge(
        depo_non_sum,
        left_on="Cabang/Pusat",
        right_on=cg.cabang_pusat,
        how="left",
    )
    table_total = table_total.merge(
        giro_sum,
        left_on="Cabang/Pusat",
        right_on=cg.cabang_pusat,
        how="left",
    )
    table_total = table_total.merge(
        kas_sum,
        left_on="Cabang/Pusat",
        right_on=cg.cabang_pusat,
        how="left",
    )

    table_total = table_total.drop(
        columns=[c for c in table_total.columns if "CABANG/PUSAT" in c.upper() and c != "Cabang/Pusat"],
        errors="ignore",
    ).fillna(0)

    table_total["Total"] = (
        table_total["Total Deposito (Non Restricted)"]
        + table_total["Total Giro"]
        + table_total["Total Kas"]
    )

    for col in [
        "Total Deposito (Non Restricted)",
        "Total Giro",
        "Total Kas",
        "Total",
    ]:
        table_total[col] = table_total[col].apply(round_half_up)

    table_total.loc[len(table_total)] = [
        "Grand Total",
        table_total["Total Deposito (Non Restricted)"].sum(),
        table_total["Total Giro"].sum(),
        table_total["Total Kas"].sum(),
        table_total["Total"].sum(),
    ]

    # =====================================================
    # GRAFIK TREND
    # =====================================================
    total = total.sort_values(ct.tahun)
    total["YoY Change %"] = total[ct.total].pct_change() * 100

    bar_texts = []
    first_index = total.index.min() if not total.empty else None

    for idx, row in total.iterrows():
        val_text = f"{row[ct.total]:,.0f}"

        if idx != first_index and pd.notna(row["YoY Change %"]):
            yoy = row["YoY Change %"]
            if yoy > 0:
                bar_texts.append(f"{val_text}<br>↑ {yoy:.1f}%")
            elif yoy < 0:
                bar_texts.append(f"{val_text}<br>↓ {abs(yoy):.1f}%")
            else:
                bar_texts.append(f"{val_text}<br>0.0%")
        else:
            bar_texts.append(val_text)

    fig_bar = go.Figure()
    fig_bar.add_bar(
        x=total[ct.tahun],
        y=total[ct.total],
        text=bar_texts,
        textposition="outside",
        name="Total",
    )
    fig_bar.add_scatter(
        x=total[ct.tahun],
        y=total[ct.total],
        mode="lines+markers",
        name="Trend",
    )

    ymax = float(total[ct.total].max()) if not total.empty else 0
    fig_bar.update_layout(
        height=360,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        yaxis=dict(range=[0, ymax * 1.2 if ymax > 0 else 1]),
    )

    colA, colB = st.columns(2)

    with colA:
        st.subheader("Total Cash and Cash Equivalents")
        st.markdown(make_html_table(table_total, "Cabang/Pusat"), unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-style:italic; margin-top:6px;'>"
            f"*Exclude Restricted Deposito: {round_half_up(restricted_total):,.0f}*"
            f"</div>",
            unsafe_allow_html=True,
        )

    with colB:
        st.subheader("Cash and Cash Equivalents Trend")
        st.plotly_chart(fig_bar, use_container_width=True)

    # =====================================================
    # DETAIL PER BANK
    # =====================================================
    giro_pusat = giro[giro[cg.cabang_pusat] == "PUSAT"]
    giro_cabang = giro[giro[cg.cabang_pusat] == "CABANG"]

    unique_banks = (
        gd[cg.bank]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
    )

    df_detail = (
        pd.DataFrame({cg.bank: unique_banks})
        .merge(
            giro_pusat.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Giro Pusat"}),
            on=cg.bank,
            how="left",
        )
        .merge(
            giro_cabang.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Giro Cabang"}),
            on=cg.bank,
            how="left",
        )
        .merge(
            deposito_non.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Deposito (Non Restricted)"}),
            on=cg.bank,
            how="left",
        )
        .merge(
            kas.groupby(cg.bank, as_index=False)[cg.saldo]
            .sum()
            .rename(columns={cg.saldo: "Kas"}),
            on=cg.bank,
            how="left",
        )
        .fillna(0)
    )

    df_detail["Total"] = (
        df_detail["Giro Pusat"]
        + df_detail["Giro Cabang"]
        + df_detail["Deposito (Non Restricted)"]
        + df_detail["Kas"]
    )

    for col in ["Giro Pusat", "Giro Cabang", "Deposito (Non Restricted)", "Kas", "Total"]:
        df_detail[col] = df_detail[col].apply(round_half_up)

    df_detail = df_detail.sort_values("Total", ascending=False)

    df_detail.loc[len(df_detail)] = [
        "Grand Total",
        df_detail["Giro Pusat"].sum(),
        df_detail["Giro Cabang"].sum(),
        df_detail["Deposito (Non Restricted)"].sum(),
        df_detail["Kas"].sum(),
        df_detail["Total"].sum(),
    ]

    color_map = {
        "BRI": "#0A3185",
        "BSI": "#00A39D",
        "BTN": "#0057B8",
        "BNI": "#F37021",
        "MANDIRI": "#002F6C",
        "CIMB": "#990000",
        "BJB": "#AB9B56",
        "BCA": "#00529B",
        "BANK RAYA": "#00549A",
        "BTN SYARIAH": "#FFC20E",
        "BRI USD": "#0A3185",
        "BCA SYARIAH": "#00979D",
        "KAS": "#D3D3D3",
    }

    pie_data = df_detail[df_detail[cg.bank] != "Grand Total"].copy()
    total_pie = pie_data["Total"].sum()

    fig_pie = go.Figure(
        data=[
            go.Pie(
                labels=pie_data[cg.bank],
                values=pie_data["Total"],
                text=[
                    f"{bank}<br>{(value / total_pie) * 100:.1f}%"
                    if total_pie > 0 else f"{bank}<br>0.0%"
                    for bank, value in zip(pie_data[cg.bank], pie_data["Total"])
                ],
                textinfo="text",
                textposition="outside",
                pull=[0.03] * len(pie_data),
                marker=dict(colors=[color_map.get(b, "#CCCCCC") for b in pie_data[cg.bank]]),
                hole=0.35,
            )
        ]
    )

    fig_pie.update_layout(
        height=450,
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=False,
    )

    col1, col2 = st.columns([1.1, 0.9])

    with col1:
        st.subheader("Cash and Cash Equivalents Details per Bank")
        st.markdown(make_html_table(df_detail, cg.bank), unsafe_allow_html=True)

    with col2:
        st.subheader("% Cash and Equivalents per Bank (Exclude Restricted)")
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown(
        "<div class='footer-credit'>Created by Nur Vita Anajningrum</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
