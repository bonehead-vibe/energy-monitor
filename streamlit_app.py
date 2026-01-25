import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- SETUP ---
st.set_page_config(page_title="Gutsweg 3", layout="wide")

# CSS für bessere mobile Darstellung (Padding und Schrift)
st.markdown("""
    <style>
    .main { padding-top: 1rem; }
    .stMetric { background-color: rgba(28, 131, 225, 0.1); padding: 10px; border-radius: 10px; }
    [data-testid="column"] { width: 100% !important; flex: 1 1 calc(50% - 1rem) !important; min-width: 150px !important; }
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

    numeric_cols = ['Strombezug kWh', 'Fernwärmebezug (kWh)', 'PV Produktion (kWh)', 'Einspeisung', 'Eigenverbrauch', 'Wasser m³', 'Wasserkosten (€)']
    for col in numeric_cols:
        if col in raw_df.columns: raw_df[col] = raw_df[col].apply(clean_val)
    
    if 'Strombezug kWh' in raw_df.columns:
        raw_df.loc[(raw_df['Strombezug kWh'] < 0) | (raw_df['Strombezug kWh'] > 1000), 'Strombezug kWh'] = None

    raw_df['Jahr'] = pd.to_numeric(raw_df['Jahr'], errors='coerce').fillna(0).astype(int)
    raw_df['Monat_Kurz'] = raw_df['Monat'].str.strip().map(MONTH_MAP)
    df = raw_df[(raw_df['Jahr'] > 2010) & (raw_df['Monat_Kurz'].notna())].copy()
    df['Monat_Kurz'] = pd.Categorical(df['Monat_Kurz'], categories=MONTH_ORDER, ordered=True)
    return df

try:
    df = load_data()
    st.title("🏡 Gutsweg 3")

    # --- SIDEBAR ---
    all_years = sorted(df['Jahr'].unique(), reverse=True)
    st.sidebar.header("Optionen")
    selected_year_pv = st.sidebar.selectbox("Fokus-Jahr:", options=all_years, index=0)
    compare_years = st.sidebar.multiselect("Vergleich:", options=all_years, default=all_years[:2])

    df_plot = df[df['Jahr'].isin(compare_years)].sort_values(['Jahr', 'Monat_Kurz'])
    avg_df = df.groupby('Monat_Kurz', observed=True).mean(numeric_only=True).reset_index()
    yearly_all = df.groupby('Jahr').sum(numeric_only=True).reset_index().sort_values('Jahr')

    # --- KPIs (Mobil optimiert: 2 Spalten Layout) ---
    st.subheader("Jahres-Check")
    for year in sorted(compare_years):
        y_sum = yearly_all[yearly_all['Jahr'] == year]
        prev_sum = yearly_all[yearly_all['Jahr'] == (year - 1)]
        k1, k2 = st.columns(2)
        with k1:
            fw_val = y_sum['Fernwärmebezug (kWh)'].values[0]
            fw_delta = f"{((fw_val - prev_sum['Fernwärmebezug (kWh)'].values[0]) / prev_sum['Fernwärmebezug (kWh)'].values[0] * 100):+.1f}%" if not prev_sum.empty else None
            st.metric(f"Wärme {year}", f"{fw_val:,.0f} kWh".replace(",", "."), delta=fw_delta, delta_color="inverse")
        with k2:
            st_val = y_sum['Strombezug kWh'].values[0]
            st_delta = f"{((st_val - prev_sum['Strombezug kWh'].values[0]) / prev_sum['Strombezug kWh'].values[0] * 100):+.1f}%" if not prev_sum.empty else None
            st.metric(f"Strom {year}", f"{st_val:,.1f} kWh".replace(",", "."), delta=st_delta, delta_color="inverse")

    # --- TABS ---
    tab1, tab2, tab3 = st.tabs(["🔥 Wärme", "🔌 Strom", "💧 Wasser"])

    def apply_mobile_style(fig):
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=-0.5, xanchor="center", x=0.5),
            margin=dict(l=10, r=10, t=40, b=10),
            hovermode="x unified"
        )
        fig.update_yaxes(rangemode='tozero', autorange=True)
        return fig

    with tab1:
        fig_l1 = go.Figure()
        fig_l1.add_trace(go.Scatter(x=avg_df['Monat_Kurz'], y=avg_df['Fernwärmebezug (kWh)'], name="Schnitt", line=dict(color='#FF8C00', dash='dot')))
        for yr in sorted(compare_years):
            yr_data = df_plot[df_plot['Jahr'] == yr]
            fig_l1.add_trace(go.Scatter(x=yr_data['Monat_Kurz'], y=yr_data['Fernwärmebezug (kWh)'], name=str(yr)))
        st.plotly_chart(apply_mobile_style(fig_l1), use_container_width=True)
        
        fig_b1 = px.bar(yearly_all, x='Jahr', y='Fernwärmebezug (kWh)', title="Trend Jahre (kWh)", text_auto='.0f', color_discrete_sequence=['#EF553B'])
        st.plotly_chart(apply_mobile_style(fig_b1), use_container_width=True)

    with tab2:
        # Strom-Verlauf
        fig_l2 = go.Figure()
        fig_l2.add_trace(go.Scatter(x=avg_df['Monat_Kurz'], y=avg_df['Strombezug kWh'], name="Schnitt", line=dict(color='#FF8C00', dash='dot')))
        for yr in sorted(compare_years):
            yr_data = df_plot[df_plot['Jahr'] == yr]
            fig_l2.add_trace(go.Scatter(x=yr_data['Monat_Kurz'], y=yr_data['Strombezug kWh'], name=str(yr)))
        st.plotly_chart(apply_mobile_style(fig_l2), use_container_width=True)

        # Bilanz & Quote (Untereinander auf Mobil)
        st.markdown(f"**Eigenverbrauch {selected_year_pv}**")
        pv_year = df[df['Jahr'] == selected_year_pv]
        eigen, einsp, prod = pv_year['Eigenverbrauch'].sum(), pv_year['Einspeisung'].sum(), pv_year['PV Produktion (kWh)'].sum()
        
        if prod > 0:
            fig_p = px.pie(values=[eigen, einsp], names=['Eigen', 'Netz'], color_discrete_sequence=['#00CC96', '#9ea0a1'], hole=0.4)
            fig_p.update_layout(showlegend=True, height=300)
            st.plotly_chart(apply_mobile_style(fig_p), use_container_width=True)
            
            fig_bilanz = go.Figure()
            fig_bilanz.add_trace(go.Bar(x=pv_year['Monat_Kurz'], y=pv_year['Strombezug kWh'], name='Netz', marker_color='#636EFA'))
            fig_bilanz.add_trace(go.Bar(x=pv_year['Monat_Kurz'], y=pv_year['Eigenverbrauch'], name='PV', marker_color='#00CC96'))
            fig_bilanz.add_trace(go.Bar(x=pv_year['Monat_Kurz'], y=pv_year['Einspeisung'], name='Export', marker_color='#9ea0a1'))
            fig_bilanz.update_layout(barmode='stack', title="Energie-Mix")
            st.plotly_chart(apply_mobile_style(fig_bilanz), use_container_width=True)

    with tab3:
        fig_w1 = px.bar(yearly_all, x='Jahr', y='Wasser m³', title="Wasser m³", text_auto='.1f', color_discrete_sequence=['#00CC96'])
        st.plotly_chart(apply_mobile_style(fig_w1), use_container_width=True)
        fig_w2 = px.bar(yearly_all, x='Jahr', y='Wasserkosten (€)', title="Kosten €", text_auto='.0f', color_discrete_sequence=['#AB63FA'])
        st.plotly_chart(apply_mobile_style(fig_w2), use_container_width=True)

except Exception as e:
    st.error(f"Datenfehler: {e}")