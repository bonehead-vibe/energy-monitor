import datetime
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from openai import OpenAI
# --- PAGE CONFIG ---
st.set_page_config(
    page_title="G3 Energie Dashboard",
    page_icon="🏡",
    layout="wide",
)
# --- CSS ---
st.markdown(
    """
    <style>
    .main { padding-top: 1rem; }
    .stMetric {
        background-color: rgba(28, 131, 225, 0.1);
        padding: 10px;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# --- PASSWORD ---
def check_password() -> bool:
    def password_entered():
        if st.session_state["password"] == st.secrets.get("APP_PASSWORD", ""):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "APP_PASSWORD" not in st.secrets:
        st.error("Fehler: APP_PASSWORD nicht in den Streamlit Secrets gefunden.")
        return False
    if "password_correct" not in st.session_state:
        st.text_input(
            "Bitte Passwort eingeben",
            type="password",
            on_change=password_entered,
            key="password",
        )
        return False
    if not st.session_state["password_correct"]:
        st.text_input(
            "Bitte Passwort eingeben",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("Passwort falsch")
        return False
    return True
if not check_password():
    st.stop()
# --- SECRETS ---
if "SHEET_ID" not in st.secrets:
    st.error("Fehler: SHEET_ID nicht in den Streamlit Secrets gefunden.")
    st.stop()
SHEET_ID = st.secrets["SHEET_ID"]
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
# --- CONSTANTS ---
MONTH_MAP = {
    "1": "Jan",
    "2": "Feb",
    "3": "Mär",
    "4": "Apr",
    "5": "Mai",
    "6": "Jun",
    "7": "Jul",
    "8": "Aug",
    "9": "Sep",
    "10": "Okt",
    "11": "Nov",
    "12": "Dez",
    "Januar": "Jan",
    "Februar": "Feb",
    "März": "Mär",
    "April": "Apr",
    "Mai": "Mai",
    "Juni": "Jun",
    "Juli": "Jul",
    "August": "Aug",
    "September": "Sep",
    "Oktober": "Okt",
    "November": "Nov",
    "Dezember": "Dez",
}
MONTH_ORDER = [
    "Jan",
    "Feb",
    "Mär",
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
]
NUMERIC_COLS = [
    "Strombezug kWh",
    "Fernwärmebezug (kWh)",
    "PV Produktion (kWh)",
    "Einspeisung",
    "Eigenverbrauch",
    "Wasser m³",
    "Wasserkosten (€)",
    "Stromkosten (€)",
    "Fernwärmekosten (€)",
]
# --- HELPERS ---
def clean_val(val) -> float:
    if pd.isna(val) or str(val).strip() in ["", "-", "None", "-1"]:
        return 0.0
    s = "".join(c for c in str(val) if c.isdigit() or c in ",.")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", "") if len(parts[-1]) == 3 else s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0
def mean_plausible(series: pd.Series, limit: float) -> float:
    valid = series[(series > 0) & (series < limit)]
    return float(valid.mean()) if not valid.empty else 0.0
def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return np.where(denominator > 0, numerator / denominator, np.nan)
def apply_style(fig):
    fig.update_layout(
        legend=dict(orientation="h", y=-0.35),
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig
@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    raw_df = pd.read_csv(SHEET_URL, dtype=str)
    required_base_cols = ["Jahr", "Monat"]
    missing_base_cols = [col for col in required_base_cols if col not in raw_df.columns]
    if missing_base_cols:
        raise ValueError(f"Pflichtspalten fehlen im Google Sheet: {missing_base_cols}")
    for col in NUMERIC_COLS:
        if col not in raw_df.columns:
            raw_df[col] = 0.0
        else:
            raw_df[col] = raw_df[col].apply(clean_val)
    # Ausreißer / ungültige Werte
    raw_df.loc[
        (raw_df["Strombezug kWh"] < 0) | (raw_df["Strombezug kWh"] > 1500),
        "Strombezug kWh",
    ] = np.nan
    raw_df.loc[
        raw_df["Fernwärmebezug (kWh)"] < 0,
        "Fernwärmebezug (kWh)",
    ] = np.nan
    raw_df["Jahr_Clean"] = (
        pd.to_numeric(raw_df["Jahr"].astype(str).str.strip(), errors="coerce")
        .fillna(0)
        .astype(int)
    )
    raw_df["Monat_Kurz"] = raw_df["Monat"].astype(str).str.strip().map(MONTH_MAP)
    current_year = datetime.datetime.now().year
    df = raw_df[
        (raw_df["Jahr_Clean"] > 2010)
        & (raw_df["Jahr_Clean"] <= current_year)
        & (raw_df["Monat_Kurz"].notna())
    ].copy()
    df["Jahr"] = df["Jahr_Clean"]
    df["Monat_Kurz"] = pd.Categorical(
        df["Monat_Kurz"],
        categories=MONTH_ORDER,
        ordered=True,
    )
    return df
def build_yearly_data(df: pd.DataFrame) -> pd.DataFrame:
    yearly = (
        df.groupby("Jahr", observed=True)
        .sum(numeric_only=True)
        .reset_index()
        .sort_values("Jahr")
    )
    yearly["€/kWh_FW"] = safe_divide(
        yearly["Fernwärmekosten (€)"],
        yearly["Fernwärmebezug (kWh)"],
    )
    yearly["€/kWh_ST"] = safe_divide(
        yearly["Stromkosten (€)"],
        yearly["Strombezug kWh"],
    )
    yearly["€/m³_W"] = safe_divide(
        yearly["Wasserkosten (€)"],
        yearly["Wasser m³"],
    )
    return yearly
def build_avg_data(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("Monat_Kurz", observed=True)
        .agg(
            {
                "Strombezug kWh": lambda x: mean_plausible(x, 1000),
                "Fernwärmebezug (kWh)": lambda x: mean_plausible(x, 2500),
                "Wasser m³": lambda x: mean_plausible(x, 50),
                "Wasserkosten (€)": lambda x: mean_plausible(x, 200),
            }
        )
        .reset_index()
    )
def pct_change(current: float, previous: float):
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)
def build_ai_payload(df: pd.DataFrame, yearly_all: pd.DataFrame, selected_year: int) -> dict:
    latest_year = int(yearly_all["Jahr"].max())
    previous_year = latest_year - 1
    latest = yearly_all[yearly_all["Jahr"] == latest_year].iloc[0]
    previous_rows = yearly_all[yearly_all["Jahr"] == previous_year]
    previous = previous_rows.iloc[0] if not previous_rows.empty else None
    yearly_records = yearly_all[
        [
            "Jahr",
            "Strombezug kWh",
            "Stromkosten (€)",
            "€/kWh_ST",
            "Fernwärmebezug (kWh)",
            "Fernwärmekosten (€)",
            "€/kWh_FW",
            "Wasser m³",
            "Wasserkosten (€)",
            "€/m³_W",
            "PV Produktion (kWh)",
            "Eigenverbrauch",
            "Einspeisung",
        ]
    ].tail(6)
    monthly = df[df["Jahr"] == selected_year].copy()
    anomaly_rows = []
    for col, label, limit_pct in [
        ("Strombezug kWh", "Strom", 35),
        ("Fernwärmebezug (kWh)", "Fernwärme", 35),
        ("Wasser m³", "Wasser", 35),
    ]:
        month_avg = df.groupby("Monat_Kurz", observed=True)[col].mean()
        for _, row in monthly.iterrows():
            month = row["Monat_Kurz"]
            value = row[col]
            avg = month_avg.get(month)
            if pd.notna(value) and pd.notna(avg) and avg > 0:
                deviation = (value - avg) / avg * 100
                if abs(deviation) >= limit_pct:
                    anomaly_rows.append(
                        {
                            "jahr": int(row["Jahr"]),
                            "monat": str(month),
                            "bereich": label,
                            "wert": round(float(value), 2),
                            "durchschnitt": round(float(avg), 2),
                            "abweichung_prozent": round(float(deviation), 1),
                        }
                    )
    payload = {
        "hinweis": "Dies sind aggregierte Kennzahlen, keine Rohdaten aus dem Google Sheet.",
        "latest_year": latest_year,
        "selected_analysis_year": selected_year,
        "latest_year_summary": {
            "strom_kwh": round(float(latest["Strombezug kWh"]), 1),
            "stromkosten_eur": round(float(latest["Stromkosten (€)"]), 2),
            "strompreis_eur_kwh": None
            if pd.isna(latest["€/kWh_ST"])
            else round(float(latest["€/kWh_ST"]), 4),
            "fernwaerme_kwh": round(float(latest["Fernwärmebezug (kWh)"]), 1),
            "fernwaermekosten_eur": round(float(latest["Fernwärmekosten (€)"]), 2),
            "fernwaermepreis_eur_kwh": None
            if pd.isna(latest["€/kWh_FW"])
            else round(float(latest["€/kWh_FW"]), 4),
            "wasser_m3": round(float(latest["Wasser m³"]), 1),
            "wasserkosten_eur": round(float(latest["Wasserkosten (€)"]), 2),
            "wasserpreis_eur_m3": None
            if pd.isna(latest["€/m³_W"])
            else round(float(latest["€/m³_W"]), 4),
            "pv_produktion_kwh": round(float(latest["PV Produktion (kWh)"]), 1),
            "pv_eigenverbrauch_kwh": round(float(latest["Eigenverbrauch"]), 1),
            "pv_einspeisung_kwh": round(float(latest["Einspeisung"]), 1),
        },
        "change_vs_previous_year_pct": {},
        "last_6_years": yearly_records.replace({np.nan: None}).round(4).to_dict("records"),
        "anomalies_selected_year": anomaly_rows[:15],
    }
    if previous is not None:
        payload["change_vs_previous_year_pct"] = {
            "strom_kwh": pct_change(
                latest["Strombezug kWh"],
                previous["Strombezug kWh"],
            ),
            "stromkosten": pct_change(
                latest["Stromkosten (€)"],
                previous["Stromkosten (€)"],
            ),
            "fernwaerme_kwh": pct_change(
                latest["Fernwärmebezug (kWh)"],
                previous["Fernwärmebezug (kWh)"],
            ),
            "fernwaermekosten": pct_change(
                latest["Fernwärmekosten (€)"],
                previous["Fernwärmekosten (€)"],
            ),
            "wasser_m3": pct_change(
                latest["Wasser m³"],
                previous["Wasser m³"],
            ),
            "wasserkosten": pct_change(
                latest["Wasserkosten (€)"],
                previous["Wasserkosten (€)"],
            ),
        }
    return payload
def run_ai_analysis(payload: dict, user_question: str | None = None) -> str:
    if "OPENAI_API_KEY" not in st.secrets:
        return "OPENAI_API_KEY ist nicht in den Streamlit Secrets hinterlegt."
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    if user_question:
        task = f"""
Beantworte die folgende Frage zu den Energiedaten:
Frage:
{user_question}
"""
    else:
        task = """
Erstelle eine sachliche Energieanalyse für den Eigentümer des Hauses.
Fokus:
- wichtigste Auffälligkeiten
- Verbrauchsentwicklung
- Kostenentwicklung
- mögliche Einsparpotenziale
- Datenqualitätsrisiken
- konkrete nächste Schritte
"""
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=f"""
Du bist ein sachlicher Energieanalyst.
Nutze ausschließlich die folgenden aggregierten Daten.
Wenn die Daten nicht ausreichen, sage das klar.
Erfinde keine Werte.
Aggregierte Daten:
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
Aufgabe:
{task}
""",
    )
    return response.output_text
# --- APP ---
try:
    df = load_data()
    yearly_all = build_yearly_data(df)
    avg_df = build_avg_data(df)
    st.title("🏡 G3 Energie Dashboard")
    if df.empty:
        st.warning("Keine gültigen Daten gefunden.")
        st.stop()
    all_years = sorted(df["Jahr"].unique(), reverse=True)
    st.sidebar.header("Filter & Fokus")
    selected_year_pv = st.sidebar.selectbox(
        "Fokus-Jahr PV / KI-Analyse:",
        options=all_years,
        index=0,
    )
    compare_years = st.sidebar.multiselect(
        "Jahre im Vergleich:",
        options=all_years,
        default=all_years[:2],
    )
    df_plot = df[df["Jahr"].isin(compare_years)].sort_values(["Jahr", "Monat_Kurz"])
    # --- KPIs ---
    st.subheader("Jahres-Check")
    if compare_years:
        kpi_cols = st.columns(len(compare_years))
        for i, year in enumerate(sorted(compare_years)):
            y_sum = yearly_all[yearly_all["Jahr"] == year]
            if y_sum.empty:
                continue
            y_sum = y_sum.iloc[0]
            with kpi_cols[i]:
                st.info(f"📅 **Jahr {year}**")
                st.metric(
                    "Fernwärme",
                    f"{int(y_sum['Fernwärmebezug (kWh)']):,}".replace(",", ".") + " kWh",
                )
                st.metric(
                    "Strombezug",
                    f"{int(y_sum['Strombezug kWh']):,}".replace(",", ".") + " kWh",
                )
                st.metric(
                    "Wasser",
                    f"{float(y_sum['Wasser m³']):,.1f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                    + " m³",
                )
    else:
        st.warning("Bitte mindestens ein Vergleichsjahr auswählen.")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["🔥 Wärme", "🔌 Strom", "💧 Wasser", "🤖 KI-Analyse"]
    )
    # --- WÄRME ---
    with tab1:
        fig_l1 = go.Figure()
        fig_l1.add_trace(
            go.Scatter(
                x=avg_df["Monat_Kurz"],
                y=avg_df["Fernwärmebezug (kWh)"],
                name="Schnitt",
                line=dict(dash="dot"),
            )
        )
        for yr in sorted(compare_years):
            yr_data = df_plot[df_plot["Jahr"] == yr]
            fig_l1.add_trace(
                go.Scatter(
                    x=yr_data["Monat_Kurz"],
                    y=yr_data["Fernwärmebezug (kWh)"],
                    name=str(yr),
                )
            )
        fig_l1.update_layout(title="Fernwärme monatlich")
        st.plotly_chart(apply_style(fig_l1), width="stretch")
        st.plotly_chart(
            px.bar(
                yearly_all,
                x="Jahr",
                y="Fernwärmebezug (kWh)",
                title="Trend Fernwärme Jahre (kWh)",
                text_auto=".0f",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.bar(
                yearly_all,
                x="Jahr",
                y="Fernwärmekosten (€)",
                title="Trend Fernwärme Jahre (€)",
                text_auto=".0f",
                color_discrete_sequence=["#EF553B"],
            ),
            width="stretch",
        )
        fig_fw_ratio = px.line(
            yearly_all,
            x="Jahr",
            y="€/kWh_FW",
            title="Fernwärme: € je kWh",
            markers=True,
            color_discrete_sequence=["#EF553B"],
        )
        fig_fw_ratio.update_yaxes(range=[0, None])
        st.plotly_chart(apply_style(fig_fw_ratio), width="stretch")
    # --- STROM ---
    with tab2:
        fig_l2 = go.Figure()
        fig_l2.add_trace(
            go.Scatter(
                x=avg_df["Monat_Kurz"],
                y=avg_df["Strombezug kWh"],
                name="Schnitt",
                line=dict(dash="dot"),
            )
        )
        for yr in sorted(compare_years):
            yr_data = df_plot[df_plot["Jahr"] == yr]
            fig_l2.add_trace(
                go.Scatter(
                    x=yr_data["Monat_Kurz"],
                    y=yr_data["Strombezug kWh"],
                    name=str(yr),
                )
            )
        fig_l2.update_layout(title="Strombezug monatlich")
        st.plotly_chart(apply_style(fig_l2), width="stretch")
        st.markdown(f"### PV-Bilanz Fokus-Jahr {selected_year_pv}")
        df_pv = df[df["Jahr"] == selected_year_pv].sort_values("Monat_Kurz")
        if not df_pv.empty:
            col_a, col_b = st.columns(2)
            with col_a:
                pv_totals = df_pv[["Eigenverbrauch", "Einspeisung"]].sum()
                fig_pie = px.pie(
                    values=pv_totals,
                    names=pv_totals.index,
                    title="Nutzung PV-Strom",
                    color=pv_totals.index,
                    color_discrete_map={
                        "Eigenverbrauch": "#00CC96",
                        "Einspeisung": "#ABB2B9",
                    },
                )
                st.plotly_chart(fig_pie, width="stretch")
            with col_b:
                fig_stack = go.Figure()
                fig_stack.add_trace(
                    go.Bar(
                        x=df_pv["Monat_Kurz"],
                        y=df_pv["Strombezug kWh"],
                        name="Netzbezug",
                        marker_color="#636EFA",
                    )
                )
                fig_stack.add_trace(
                    go.Bar(
                        x=df_pv["Monat_Kurz"],
                        y=df_pv["Eigenverbrauch"],
                        name="PV Eigenverbrauch",
                        marker_color="#00CC96",
                    )
                )
                fig_stack.add_trace(
                    go.Bar(
                        x=df_pv["Monat_Kurz"],
                        y=df_pv["Einspeisung"],
                        name="Netzeinspeisung",
                        marker_color="#ABB2B9",
                    )
                )
                fig_stack.update_layout(
                    barmode="stack",
                    title=f"Strom-Mix & Bilanz {selected_year_pv}",
                )
                st.plotly_chart(fig_stack, width="stretch")
        st.plotly_chart(
            px.bar(
                yearly_all,
                x="Jahr",
                y="Strombezug kWh",
                title="Trend Strom Jahre (kWh)",
                text_auto=".0f",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.bar(
                yearly_all,
                x="Jahr",
                y="Stromkosten (€)",
                title="Trend Strom Jahre (€)",
                text_auto=".0f",
                color_discrete_sequence=["#636EFA"],
            ),
            width="stretch",
        )
        fig_st_ratio = px.line(
            yearly_all,
            x="Jahr",
            y="€/kWh_ST",
            title="Strom: € je kWh",
            markers=True,
            color_discrete_sequence=["#636EFA"],
        )
        fig_st_ratio.update_yaxes(range=[0, None])
        st.plotly_chart(apply_style(fig_st_ratio), width="stretch")
    # --- WASSER ---
    with tab3:
        st.plotly_chart(
            px.bar(
                yearly_all,
                x="Jahr",
                y="Wasser m³",
                title="Wasserverbrauch Jahre (m³)",
                text_auto=".1f",
            ),
            width="stretch",
        )
        st.plotly_chart(
            px.bar(
                yearly_all,
                x="Jahr",
                y="Wasserkosten (€)",
                title="Wasserkosten Jahre (€)",
                text_auto=".0f",
            ),
            width="stretch",
        )
        fig_w_ratio = px.line(
            yearly_all,
            x="Jahr",
            y="€/m³_W",
            title="Wasser: € je m³",
            markers=True,
            color_discrete_sequence=["#00CC96"],
        )
        fig_w_ratio.update_yaxes(range=[0, None])
        st.plotly_chart(apply_style(fig_w_ratio), width="stretch")
    # --- KI ---
    with tab4:
        st.subheader("KI-Auswertung auf Basis aggregierter Daten")
        payload = build_ai_payload(df, yearly_all, selected_year_pv)
        with st.expander("An OpenAI gesendete aggregierte Daten anzeigen"):
            st.json(payload)
        st.info(
            "Es werden keine vollständigen Rohdaten aus dem Google Sheet gesendet, "
            "sondern nur Jahreswerte, Vorjahresvergleiche und erkannte Auffälligkeiten."
        )
        if st.button("Automatische Analyse erstellen"):
            with st.spinner("Analyse wird erstellt..."):
                result = run_ai_analysis(payload)
                st.markdown(result)
        st.divider()
        question = st.text_input(
            "Frage zu deinen Energiedaten",
            placeholder="z. B. Warum sind meine Wärmekosten gestiegen?",
        )
        if st.button("Frage beantworten") and question.strip():
            with st.spinner("Antwort wird erstellt..."):
                result = run_ai_analysis(payload, user_question=question.strip())
                st.markdown(result)
except Exception as e:
    if "insufficient_quota" in str(e):
        st.error(
            "OpenAI API-Guthaben aufgebraucht oder Billing nicht eingerichtet."
        )
    else:
        st.error(f"Datenfehler: {e}")
