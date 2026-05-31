import time

import pandas as pd


def build_results_frame(demand_profiles, techs, ates, timesteps, crop=None):
    results = {
        "Timestep": pd.to_datetime(timesteps.iloc[-8760:].to_numpy()),
        "Warmtevraag": demand_profiles["Heat Demand"][-8760:],
        "Aardwarmte_Output": techs["Geothermal"].direct_use[-8760:],
        "MTO_Output": techs["MTS"].direct_use[-8760:],
        "WKK_Output": techs["CHP"].direct_use[-8760:],
        "Ketel_Output": techs["Gasboiler"].direct_use[-8760:],
        "T_hot_all": ates.T_hot_all[-8760:],
        "T_cold_all": ates.T_cold_all[-8760:],
    }

    if isinstance(crop, str) and crop.strip().lower() == "Orchidee":
        results["Condenser_Output"] = techs["Condenser"].direct_use[-8760:]

    return pd.DataFrame(results)


def build_kpis(demand_profiles, techs, mto_flow_limit, runtime_start):
    mts_charging = techs["MTS"].charging[-8760:].sum()
    eff = (techs["MTS"].direct_use[-8760:].sum() / mts_charging) if mts_charging != 0 else 0
    total_heat_demand_gwh = round(demand_profiles["Heat Demand"][-8760:].sum() / 1e6, 2)

    return {
        "MTO_flow_limit": mto_flow_limit,
        "Totale warmtevraag (laatste jaar)": total_heat_demand_gwh,
        "Verplaatste GWh (laatste jaar)": round(techs["MTS"].direct_use[-8760:].sum() / 1e6, 2),
        "MTO efficiency (laatste jaar)": round(eff, 2),
        "Rekentijd_s": round(time.time() - runtime_start, 2),
        "nr_doubletten": round(techs["MTS"].nr_doubletten, 0),
    }


def build_daily_output(df_results):
    output_columns = [
        column for column in ["Aardwarmte_Output", "Condenser_Output", "MTO_Output", "WKK_Output", "Ketel_Output"]
        if column in df_results.columns
    ]
    return (
        df_results
        .set_index("Timestep")[output_columns]
        .resample("D")
        .sum()
        .reset_index()
    )
