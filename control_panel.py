"""Control panel module for running MTO thermal energy model simulations.

This module orchestrates the execution of thermal energy system simulations,
managing input processing, model initialization, simulation execution, and
output generation.
"""
import time

from calculation_model import ATESDoublet, initialize_techs, run_simulation
from input_processing import get_input
from output_generation import build_kpis, build_results_frame


def run_dashboard_calculation(file_content: bytes, crop: str, flow_mode: str | None = None, mto_flow_limit_override: float | None = None, years: int = 1, geo_power: float | None = None, chp_power: float | None = None, target_heat_demand_gwh: float | None = None, temp_cold_well: float = 25, temp_hot_well: float = 50, progress_callback=None):
    """Run a complete thermal energy system simulation.

    Executes a simulation of the ATES doublet thermal energy storage system with
    various energy technologies (geothermal, CHP, MTS). Processes input parameters,
    initializes the model, runs the simulation, and generates results and KPIs.

    Args:
        file_content (bytes): Binary content of input configuration file.
        crop (str): Crop type identifier for demand profile selection.
        flow_mode (str, optional): Flow mode setting ("High Flow" or low flow).
            Determines MTS flow limit if mto_flow_limit_override is not set.
        mto_flow_limit_override (float, optional): Direct override for MTS flow limit (m³/h).
            If provided, supersedes flow_mode setting.
        years (int, optional): Number of simulation years. Defaults to 1.
        geo_power (float, optional): Override geothermal thermal power (MW).
        chp_power (float, optional): Override CHP thermal power (MW).
        target_heat_demand_gwh (float, optional): Target annual heat demand (GWh).
        temp_cold_well (float, optional): Cold well temperature (°C). Defaults to 25.
        temp_hot_well (float, optional): Hot well temperature (°C). Defaults to 50.
        progress_callback (callable, optional): Callback function for progress updates.

    Returns:
        tuple: A tuple containing:
            - df_results (pd.DataFrame): Simulation results with timestep-level data.
            - kpis (dict): Key performance indicators including costs, efficiency, etc.
            - flow_min (float): Minimum MTS flow limit (m³/h).
            - flow_max (float): Maximum MTS flow limit (m³/h).
    """
    demand_profiles, energy_prices, n_hours, input_params, settings, timesteps = get_input(
        file_content,
        crop=crop,
        years=years,
        target_heat_demand_gwh=target_heat_demand_gwh,
    )

    if geo_power is not None:
        input_params["Geothermal"]["thermal_power"] = geo_power

    if chp_power is not None:
        input_params["CHP"]["thermal_power"] = chp_power

    flow_min = input_params["MTS"]["flow_limit_min"]
    flow_max = input_params["MTS"]["flow_limit_max"]
    if mto_flow_limit_override is not None:
        mto_flow_limit = mto_flow_limit_override
    else:
        mto_flow_limit = flow_max if flow_mode == "High Flow" else flow_min

    t0 = time.time()
    ates = ATESDoublet(factor=1.2, t_in_hot=temp_hot_well, t_in_cold=temp_cold_well, n_hours=n_hours)
    techs = initialize_techs(n_hours, input_params)
    techs["MTS"].flow_limit = mto_flow_limit

    run_simulation(
        n_hours,
        techs,
        demand_profiles,
        energy_prices,
        temp_cold_well,
        ates=ates,
        model_settings=settings,
        progress_callback=progress_callback,
    )

    df_results = build_results_frame(demand_profiles, techs, ates, timesteps, crop=crop)
    kpis = build_kpis(demand_profiles, techs, mto_flow_limit, t0)

    return df_results, kpis, flow_min, flow_max
