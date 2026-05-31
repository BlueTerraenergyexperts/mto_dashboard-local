import time

from calculation_model import ATESDoublet, initialize_techs, run_simulation
from input_processing import get_input
from output_generation import build_kpis, build_results_frame


def run_dashboard_calculation(file_content: bytes, crop: str, flow_mode: str = None, mto_flow_limit_override: float = None, years: int = 1, geo_power: float = None, chp_power: float = None, target_heat_demand_gwh: float = None, temp_cold_well: float = 25, temp_hot_well: float = 50, progress_callback=None):
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
