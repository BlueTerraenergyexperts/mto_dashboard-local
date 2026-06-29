import time

import pandas as pd


def build_results_frame(demand_profiles, techs, ates, timesteps, crop=None):
    """
    Build a pandas DataFrame containing hourly simulation results.
    
    Aggregates output from all technologies and ATES system into a single
    DataFrame with timestamps, demand, and power generation from each source.
    
    Args:
        demand_profiles (dict): Dictionary containing hourly demand data
        techs (dict): Dictionary of technology objects with simulation results
        ates (ATESDoublet): ATES doublet system with temperature histories
        timesteps (pd.Series): Series of timestamps for the simulation period
        crop (str, optional): Crop type identifier. If "orchidee", includes
            Condenser_Output column separately from Koelmachine_warmte.
            Defaults to None.
            
    Returns:
        pd.DataFrame: DataFrame with columns:
            - Timestep: Datetime index
            - Warmtevraag: Heat demand [kW]
            - Aardwarmte_Output: Geothermal heat output [kW]
            - MTO_Output: ATES system heat output [kW]
            - WKK_Output: CHP heat output [kW]
            - Ketel_Output: Gas boiler heat output [kW]
            - T_hot_all: Hot well temperature [°C]
            - T_cold_all: Cold well temperature [°C]
            - Koelmachine_warmte: Heat from condenser [kW]
            - Condenser_Output: (optional, if crop=='orchidee') Condenser output [kW]
    """
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

    if "Condenser" in techs:
        results["Koelmachine_warmte"] = techs["Condenser"].direct_use[-8760:]
        if isinstance(crop, str) and crop.strip().lower() == "orchidee":
            results["Condenser_Output"] = techs["Condenser"].direct_use[-8760:]

    return pd.DataFrame(results)


def build_kpis(demand_profiles, techs, mto_flow_limit, runtime_start):
    """
    Calculate key performance indicators (KPIs) for the simulation.
    
    Computes energy balances, efficiencies, and runtime metrics for the
    district heating system over the last simulated year (8760 hours).
    
    Args:
        demand_profiles (dict): Dictionary containing hourly demand data
        techs (dict): Dictionary of technology objects with simulation results.
            Must include 'MTS' and 'Condenser' technologies.
        mto_flow_limit (float): Maximum flow rate for ATES system [m³/h]
        runtime_start (float): Start time of simulation (as returned by time.time())
        
    Returns:
        dict: Dictionary containing KPIs:
            - MTO_flow_limit: Maximum ATES flow rate [m³/h]
            - Totale warmtevraag (laatste jaar): Total heat demand [GWh]
            - Verplaatste GWh (laatste jaar): Heat supplied by ATES [GWh]
            - MTO efficiency (laatste jaar): Roundtrip efficiency of ATES [fraction]
            - Elektriciteitsgebruik: Total electricity use for heat pumps [GWh]
            - Rekentijd_s: Total simulation runtime [seconds]
            - nr_doubletten: Number of ATES doublets deployed
    """
    mts_charging = techs["MTS"].charging[-8760:].sum()
    eff = (techs["MTS"].direct_use[-8760:].sum() / mts_charging) if mts_charging != 0 else 0
    total_heat_demand_gwh = round(demand_profiles["Heat Demand"][-8760:].sum() / 1e6, 2)
    total_electricity_use_gwh = round(
        (techs["MTS"].electricity_use[-8760:].sum() + techs["Condenser"].electricity_use[-8760:].sum()) / 1e6,
        2,
    )

    return {
        "MTO_flow_limit": mto_flow_limit,
        "Totale warmtevraag (laatste jaar)": total_heat_demand_gwh,
        "Verplaatste GWh (laatste jaar)": round(techs["MTS"].direct_use[-8760:].sum() / 1e6, 2),
        "MTO efficiency (laatste jaar)": round(eff, 2),
        "Elektriciteitsgebruik": total_electricity_use_gwh,
        "Rekentijd_s": round(time.time() - runtime_start, 2),
        "nr_doubletten": round(techs["MTS"].nr_doubletten, 0),
    }


def build_daily_output(df_results):
    """
    Aggregate hourly results to daily totals by technology.
    
    Resamples hourly power generation from all technologies to daily energy
    totals. Handles optional Condenser_Output column duplication.
    
    Args:
        df_results (pd.DataFrame): Hourly results DataFrame from build_results_frame(),
            with 'Timestep' column and output columns for each technology
            
    Returns:
        pd.DataFrame: Daily aggregated energy [kWh] with columns:
            - Timestep: Date (daily resolution)
            - Aardwarmte_Output: Daily geothermal energy [kWh]
            - Koelmachine_warmte: Daily condenser heat [kWh] (if present)
            - MTO_Output: Daily ATES system energy [kWh]
            - WKK_Output: Daily CHP energy [kWh]
            - Ketel_Output: Daily gas boiler energy [kWh]
            
    Note:
        Only columns that exist in input DataFrame are included in output.
        Time index is set by Timestep column and then resampled to daily.
    """
    df = df_results.copy()
    if "Condenser_Output" in df.columns and "Koelmachine_warmte" not in df.columns:
        df["Koelmachine_warmte"] = df["Condenser_Output"]

    output_columns = [
        column for column in ["Aardwarmte_Output", "Koelmachine_warmte", "MTO_Output", "WKK_Output", "Ketel_Output"]
        if column in df.columns
    ]
    return (
        df
        .set_index("Timestep")[output_columns]
        .resample("D")
        .sum()
        .reset_index()
    )
