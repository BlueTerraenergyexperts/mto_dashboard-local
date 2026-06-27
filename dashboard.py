import hashlib
import time
from datetime import date
from io import BytesIO
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from control_panel import run_dashboard_calculation
from input_processing import list_crop_sheets
from output_generation import build_daily_output

st.set_page_config(page_title="Dashboard MTO warmteopslag", layout="wide")


def nl(waarde, decimalen=0):
    formatted = f"{waarde:,.{decimalen}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(show_spinner=False)
def cached_list_crop_sheets(file_content: bytes):
    return list_crop_sheets(file_content)


CACHE_TTL_SECONDS = 24 * 3600
CACHE_MAX_ENTRIES = 50

APP_VERSION = "0.2.1"
APP_RELEASE_DATE = date.today().isoformat()
GITHUB_URL = "https://github.com/Jlar01/mto_dashboard-local"
COMPANY_NAME = "BlueTerra"
COMPANY_URL = "https://blueterra.nl"
AUTHOR_NAME = "Jeroen Larrivee"

def _round_or_none(value: float | None, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


def build_scenario_key(file_content: bytes, crop: str, mto_flow_limit: float, years: int, geo_power: float | None, chp_power: float | None, target_heat_demand_gwh: float | None, temp_cold_well: float, temp_hot_well: float):
    file_hash = hashlib.sha256(file_content).hexdigest()
    return (
        file_hash,
        crop,
        int(years),
        _round_or_none(mto_flow_limit, 3),
        _round_or_none(geo_power, 3),
        _round_or_none(chp_power, 3),
        _round_or_none(target_heat_demand_gwh, 6),
        _round_or_none(temp_cold_well, 3),
        _round_or_none(temp_hot_well, 3),
    )


def get_cached_scenario_result(scenario_key):
    cache = st.session_state.setdefault("scenario_result_cache", {})
    now = time.time()
    expired_keys = [k for k, v in cache.items() if now - v["ts"] > CACHE_TTL_SECONDS]
    for k in expired_keys:
        cache.pop(k, None)

    item = cache.get(scenario_key)
    if item is None:
        return None, False

    item["ts"] = now
    cache[scenario_key] = item
    return item["result"], True


def set_cached_scenario_result(scenario_key, result):
    cache = st.session_state.setdefault("scenario_result_cache", {})
    now = time.time()
    cache[scenario_key] = {"ts": now, "result": result}

    while len(cache) > CACHE_MAX_ENTRIES:
        oldest_key = min(cache, key=lambda k: cache[k]["ts"])
        cache.pop(oldest_key, None)


def run_dashboard_with_progress(file_content: bytes, crop: str, mto_flow_limit: float, years: int = 3, geo_power: float = None, chp_power: float = None, target_heat_demand_gwh: float = None, temp_cold_well: float = 25, temp_hot_well: float = 50):
    progress_text = st.empty()
    progress_bar = st.progress(0)

    def update_progress(progress: int):
        progress_bar.progress(progress)
        progress_text.caption(f"Model wordt doorgerekend... {progress}%")

    results = run_dashboard_calculation(
        file_content,
        crop=crop,
        mto_flow_limit_override=mto_flow_limit,
        years=years,
        geo_power=geo_power,
        chp_power=chp_power,
        target_heat_demand_gwh=target_heat_demand_gwh,
        temp_cold_well=temp_cold_well,
        temp_hot_well=temp_hot_well,
        progress_callback=update_progress,
    )

    progress_bar.empty()
    progress_text.empty()
    return results


col_title, col_logo = st.columns([4, 1])
with col_title:
    st.title("🔥 Dashboard MTO warmteopslag")
    st.caption(
        "Rekenmodel van BlueTerra voor het simuleren van midden temperatuur warmteopslag in de bodem. "
        "Dit model is ontwikkeld vanuit het TKI project MTO in de glastuinbouw. "
        "De input voor dit model betreft een uurwaarden energieprofiel, en een lijst met parameters. "
        "Het model berekent op uurbasis de warmtemix en de ontrekkings- en injectietemperaturen van de bron. "
        "Het model gebruikt de energie-eenheid megawattuur (MWh). Om dit om te rekenen naar m³ aardgas kan je MWh "
        "vermenigvuldigen met 113,76. Dit model is gebaseerd op onderzoek van Bert Kerst en is in ontwikkeling."
    )
with col_logo:
    st.image("logo-1 BT.png", width=140)

st.sidebar.header("⚙️ Instellingen")

input_file_path = Path(__file__).resolve().parent / "MTO_model_input_opleverversie.xlsx"
if not input_file_path.exists():
    st.error(
        "Het Excel-bestand 'MTO_model_input_opleverversie.xlsx' is niet gevonden in de projectmap."
    )
    st.stop()

file_content = input_file_path.read_bytes()
crop_options = cached_list_crop_sheets(file_content)
# Filter out unwanted sheets (e.g. lijsten, eigen profiel)
crop_options = [c for c in crop_options if c.lower() not in ("lijsten", "eigen profiel")]
default_crop_ix = crop_options.index("Tomaat") if "Tomaat" in crop_options else 0
crop = st.sidebar.selectbox("🌱 Gewas / sheet", crop_options, index=default_crop_ix)

mto_flow_limit = st.sidebar.slider(
    "💧 MTO debiet (m³/h)",
    min_value=50,
    max_value=150,
    value=80,
    step=10,
    help="Stel de flow direct in tussen 50 en 150 m³/h.",
)

temp_cold_well = st.sidebar.slider(
    "❄️ Temp koude bron (°C)",
    min_value=10,
    max_value=25,
    value=15,
    step=1,
    help="Stel de temperatuur van de koude bron in.",
)

# temp_hot_well = st.sidebar.slider(
#     "🔥 Temp warme bron (°C)",
#     min_value=40,
#     max_value=60,
#     value=50,
#     step=1,
#     help="Stel de temperatuur van de warme bron in.",
# )

#temp_cold_well = 15
temp_hot_well = 50

years = st.sidebar.radio(
    "📅 Aantal simulatiejaren",
    [1, 3, 5],
    index=1,
    help="Kies het aantal jaarreeks voor de berekening.",
)

# Sliders: eerst warmtevraag, dan WKK (CHP) vermogen, dan geothermal
target_heat_demand_mwh = st.sidebar.slider(
    "🔥 Warmtevraag (MWh)",
    min_value=0.0,
    max_value=100000.0,
    value=16000.0,
    step=0.5,
    help="Stel de totale warmtevraag in MWh in (overschrijft Excel-waarde)",
)

target_heat_demand_gwh = target_heat_demand_mwh / 1000.0

chp_power = st.sidebar.slider(
    "⚡ WKK warmte (kW)",
    min_value=0.0,
    max_value=5000.0,
    value=3150.0,
    step=50.0,
    help="Pas de WKK (CHP) power aan (overschrijft Excel-waarde)",
)

geo_power = st.sidebar.slider(
    "🌡️ Aardwarmte (kW)",
    min_value=0.0,
    max_value=2000.0,
    value=700.0,
    step=100.0,
    help="Pas de geothermal power aan (overschrijft Excel-waarde)",
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Bestand:** {input_file_path.name}")
st.sidebar.markdown(f"**MTO flow limit:** {mto_flow_limit} m³/h")
st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**Versie:** {APP_VERSION}  \
"
    f"**Datum:** {APP_RELEASE_DATE}  \
"
    f"**Auteur:** {AUTHOR_NAME}  \
"
    f"[Laatste versie op GitHub]({GITHUB_URL})  \
"
    f"[{COMPANY_NAME}]({COMPANY_URL})"
)

run_requested = st.sidebar.button("▶️ Run model")
if not run_requested:
    st.sidebar.info("Klik op 'Run model' nadat u het Excel-bestand hebt geüpload en de parameters hebt ingesteld.")
    st.stop()

scenario_key = build_scenario_key(
    file_content=file_content,
    crop=crop,
    mto_flow_limit=mto_flow_limit,
    years=years,
    geo_power=geo_power,
    chp_power=chp_power,
    target_heat_demand_gwh=target_heat_demand_gwh,
    temp_cold_well=temp_cold_well,
    temp_hot_well=temp_hot_well,
)

cached_result, cache_hit = get_cached_scenario_result(scenario_key)
if cache_hit:
    df_results, kpis, flow_min, flow_max = cached_result
    st.sidebar.info("Resultaat geladen uit cache")
else:
    df_results, kpis, flow_min, flow_max = run_dashboard_with_progress(
        file_content,
        crop,
        mto_flow_limit,
        years=years,
        geo_power=geo_power,
        chp_power=chp_power,
        target_heat_demand_gwh=target_heat_demand_gwh,
        temp_cold_well=temp_cold_well,
        temp_hot_well=temp_hot_well,
    )
    set_cached_scenario_result(scenario_key, (df_results, kpis, flow_min, flow_max))
    st.sidebar.success("Berekening gereed")

st.markdown("### 📊 KPI-overzicht")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Totale warmtevraag", f"{nl(kpis['Totale warmtevraag (laatste jaar)'] * 1000, 0)} MWh")
col2.metric("Geleverde warmte MTO", f"{nl(kpis['Verplaatste GWh (laatste jaar)'] * 1000, 0)} MWh")
col3.metric("Elektriciteitsgebruik", f"{nl(kpis['Elektriciteitsgebruik'] * 1000, 0)} MWh")
col4.metric("Rendement MTO", f"{nl(kpis['MTO efficiency (laatste jaar)'] * 100, 1)}%")

st.markdown("### 📈 Warmtemix (dagsommen)")
fig = go.Figure()
df_output_dag = build_daily_output(df_results)
output_columns = [
    column for column in ["Aardwarmte_Output", "Koelmachine_warmte", "MTO_Output", "WKK_Output", "Ketel_Output"]
    if column in df_output_dag.columns
]
output_colors = {
    "Aardwarmte_Output": "#009EE0",
    "Koelmachine_warmte": "#29b5e8",
    "MTO_Output": "#3AA935",
    "WKK_Output": "#A6A6A6",
    "Ketel_Output": "#FE6D73"
}

for column in output_columns:
    fig.add_trace(
        go.Scatter(
            x=df_output_dag["Timestep"],
            y=df_output_dag[column],
            mode="lines",
            name=column,
            line=dict(width=0.8, color=output_colors[column]),
            stackgroup="warmte_output",
        )
    )

fig.update_layout(
    height=420,
    xaxis_title="Datum",
    yaxis_title="Warmte-output kWh (dagsom)",
    margin=dict(t=40, b=40),
    hovermode="x unified",
    xaxis=dict(tickformat="%d-%m-%Y"),
)
st.plotly_chart(fig, width='stretch')

st.markdown("### 🌡️ Brontemperaturen")
if {"T_hot_all", "T_cold_all"}.issubset(df_results.columns):
    n = min(8760, len(df_results))
    df_last = df_results.tail(n).reset_index(drop=True)

    fig_temp = go.Figure()
    fig_temp.add_trace(
        go.Scatter(
            x=df_last.index,
            y=df_last["T_hot_all"],
            mode="lines",
            name="Hot well",
            line=dict(color="orangered", width=1.4),
        )
    )
    fig_temp.add_trace(
        go.Scatter(
            x=df_last.index,
            y=df_last["T_cold_all"],
            mode="lines",
            name="Cold well",
            line=dict(color="royalblue", width=1.4),
        )
    )
    fig_temp.update_layout(
        height=320,
        xaxis_title="Time [hours]",
        yaxis_title="T [°C]",
        yaxis=dict(range=[0, 52]),
        margin=dict(t=30, b=30),
        hovermode="x unified",
    )
    st.plotly_chart(fig_temp, width='stretch')
else:
    st.warning("Kolommen T_hot_all en/of T_cold_all ontbreken in df_results.")

with st.expander("Toon df_results"):
    st.dataframe(df_results, width='stretch')

csv = df_results.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
st.download_button(
    "⬇️ Download df_results als CSV",
    data=csv,
    file_name=f"df_results_{crop}_flow_{mto_flow_limit}.csv",
    mime="text/csv",
)
