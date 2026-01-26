import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- SETUP ---
st.set_page_config(page_title="G3 Energie Dashboard", layout="wide")

# CSS für mobile Optimierung
st.markdown("""
    <style>
    .main { padding-top: 1rem; }
    .stMetric { background-color: rgba(28, 131, 225, 0.1); padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

SHEET_ID = "1kFfiGuXtDjn8cGya_J6pV21oWD9aNreI7LzWG6RN2so"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

MONTH_MAP = {
    '1': 'Jan', '2': 'Feb', '3': 'Mär', '4': 'Apr', '5': 'Mai', '6': 'Jun',
    '7': 'Jul', '8': 'Aug', '9': 'Sep', '10': 'Okt', '11': 'Nov', '12': 'Dez',
    'Januar': 'Jan', 'Februar': 'Feb', 'März': 'Mär', 'April': 'Apr', 'Mai': 'Mai', 'Juni': 'Jun',
    'Juli': 'Jul', 'August': 'Aug', 'September': 'Sep', 'Oktober': 'Okt', 'November': 'Nov', 'Dezember': 'Dez'
}
MONTH_ORDER = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

@st.cache_data(ttl=10)
def load_data():
    raw_df = pd.read_csv(SHEET_URL, dtype=str)
    def clean_val(val):
        if pd.isna(val) or str(val).strip() in ["", "-", "None", "-1"]: return 0.0
        s = "".join(c for c in str(val) if c.isdigit() or c in ",.")
        if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            parts = s.split(",")
            s = s.replace(",", "") if len(parts[-1]) == 3 else s.replace(",", ".")
        elif "." in s:
            parts = s.split(".")
            if len(parts[-1]) == 3: s = s.replace(".", "")
        try: return float(s)
        except: return 0.0

    # Hier sind jetzt alle Kosten-Spalten enthalten!
    numeric_cols = [
        'Strombezug kWh', 'Fernwärmebezug (kWh)', 'PV Produktion (kWh)', 
        'Einspeisung', 'Eigenverbrauch', 'Wasser m³', 'Wasserkosten (€)',
        'Stromkosten (€)', 'Fernwärmekosten (€)'
    ]
    for col in numeric_cols:
        if col in raw_df.columns: raw_df[col] = raw_df[col].apply(clean_val)
    
    raw_df['Jahr'] = pd.to_numeric(raw_df['Jahr'], errors='coerce').fillna(0).astype(int)
    raw_df['Monat_Kurz'] = raw_df['Monat'].str.strip().map(MONTH_MAP)
    df = raw_df[(raw_df['Jahr'] > 2010) & (raw_df['Monat_Kurz'].notna())].copy()
    df['Monat_Kurz'] = pd.Categorical(df['Monat_Kurz'], categories=MONTH_ORDER, ordered=True)
    return df

try:
    df = load_data()
    st.title("🏡 G3 Energie Dashboard")

    # --- SIDEBAR ---
    all_years = sorted(df['Jahr'].unique(), reverse=True)
    st.sidebar.header("Filter & Fokus")
    selected_year_pv = st.sidebar.selectbox("Fokus-Jahr PV Eigenverbrauch:", options=all_years, index=0)
    compare_years = st.sidebar.multiselect("Jahre im Vergleich:", options=all_years, default=all_years[:2])

    df_plot = df[df['Jahr'].isin(compare_years)].sort_values(['Jahr', 'Monat_Kurz'])
    
    # Mittelwert-Logik (nur Werte > 0)
    def mean_gt_zero(series):
        valid = series[series > 0]
        return valid.mean() if not valid.empty else 0.0

    avg_df = df.groupby('Monat_Kurz', observed=True).agg({
        'Strombezug kWh': mean_gt_zero,
        'Fernwärmebezug (kWh)': mean_gt_zero,
        'Wasser m³': mean_gt_zero,
        'Wasserkosten (€)': mean_gt_zero
    }).reset_index()

    yearly_all = df.groupby('Jahr').sum(numeric_only=True).reset_index().sort_values('Jahr')

    # --- JAHRES-KPIs ---
    st.subheader("Jahres-Check (Vergleich)")
    kpi_cols = st.columns(len(compare_years) if compare_years else 1)
    for i, year in enumerate(sorted(compare_years)):
        y_sum = yearly_all[yearly_all['Jahr'] == year]
        prev_sum = yearly_all[yearly_all['Jahr'] == (year - 1)]
        with kpi_cols[i]:
            st.info(f"📅 **Jahr {year}**")
            fw_val = y_sum['Fernwärmebezug (kWh)'].values[0]
            st.metric("Fernwärme", f"{int(fw_val):,}".replace(",", ".") + " kWh")
            st_val = y_sum['Strombezug kWh'].values[0]
            st.metric("Strombezug", f"{int(st_val):,}".replace(",", ".") + " kWh")

    def apply_style(fig):
        fig.update_layout(legend=dict(orientation="h", y=-0.5), margin=dict(l=10, r=10, t=40, b=10))
        return fig

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["🔥 Wärme", "🔌 Strom", "💧 Wasser"])

    with tab1:
        # Verbrauch
        fig_l1 = go.Figure()
        fig_l1.add_trace(go.Scatter(x=avg_df['Monat_Kurz'], y=avg_df['Fernwärmebezug (kWh)'], name="Schnitt", line=dict(dash='dot')))
        for yr in sorted(compare_years):
            yr_data = df_plot[df_plot['Jahr'] == yr]
            fig_l1.add_trace(go.Scatter(x=yr_data['Monat_Kurz'], y=yr_data['Fernwärmebezug (kWh)'], name=str(yr)))
        st.plotly_chart(apply_style(fig_l1), width='stretch')
        
        st.plotly_chart(px.bar(yearly_all, x='Jahr', y='Fernwärmebezug (kWh)', title="Trend Jahre (kWh)", text_auto='.0f'), width='stretch')
        
        # NEU: Kosten
        st.plotly_chart(px.bar(yearly_all, x='Jahr', y='Fernwärmekosten (€)', title="Trend Jahre (€)", text_auto='.0f', color_discrete_sequence=['#EF553B']), width='stretch')
        
        yearly_all['€/kWh_FW'] = yearly_all['Fernwärmekosten (€)'] / yearly_all['Fernwärmebezug (kWh)']
        st.plotly_chart(px.line(yearly_all, x='Jahr', y='€/kWh_FW', title="€ je kWh (jährlich)", markers=True, color_discrete_sequence=['#EF553B']), width='stretch')

    with tab2:
        # Verbrauch
        fig_l2 = go.Figure()
        fig_l2.add_trace(go.Scatter(x=avg_df['Monat_Kurz'], y=avg_df['Strombezug kWh'], name="Schnitt", line=dict(dash='dot')))
        for yr in sorted(compare_years):
            yr_data = df_plot[df_plot['Jahr'] == yr]
            fig_l2.add_trace(go.Scatter(x=yr_data['Monat_Kurz'], y=yr_data['Strombezug kWh'], name=str(yr)))
        st.plotly_chart(apply_style(fig_l2), width='stretch')

        st.plotly_chart(px.bar(yearly_all, x='Jahr', y='Strombezug kWh', title="Trend Strom Jahre (kWh)", text_auto='.0f'), width='stretch')
        
        # NEU: Kosten
        st.plotly_chart(px.bar(yearly_all, x='Jahr', y='Stromkosten (€)', title="Trend Jahre (€)", text_auto='.0f', color_discrete_sequence=['#636EFA']), width='stretch')
        
        yearly_all['€/kWh_ST'] = yearly_all['Stromkosten (€)'] / yearly_all['Strombezug kWh']
        st.plotly_chart(px.line(yearly_all, x='Jahr', y='€/kWh_ST', title="€ je kWh (jährlich)", markers=True, color_discrete_sequence=['#636EFA']), width='stretch')

    with tab3:
        st.plotly_chart(px.bar(yearly_all, x='Jahr', y='Wasser m³', title="Wasser m³", text_auto='.1f'), width='stretch')
        st.plotly_chart(px.bar(yearly_all, x='Jahr', y='Wasserkosten (€)', title="Wasserkosten (€)", text_auto='.0f'), width='stretch')
        
        # NEU: Euro pro m3
        yearly_all['€/m³_W'] = yearly_all['Wasserkosten (€)'] / yearly_all['Wasser m³']
        st.plotly_chart(px.line(yearly_all, x='Jahr', y='€/m³_W', title="€ je m³ (jährlich)", markers=True, color_discrete_sequence=['#00CC96']), width='stretch')

except Exception as e:
    st.error(f"Datenfehler: {e}")
