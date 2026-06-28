"""Input processing module for thermal energy model configuration.

This module handles reading and processing input data from Excel configuration
files, including demand profiles, energy prices, and system parameters.
"""
from io import BytesIO

import numpy as np
import pandas as pd


def get_input(file_content: bytes, crop="Tomaat", years=1, target_heat_demand_gwh=None):
    """Read and process input data from an Excel configuration file.

    Loads demand profiles, energy prices, and system parameters from an Excel file.
    Scales demand profiles if a target heat demand is specified. Replicates data
    across multiple years if requested.

    Args:
        file_content (bytes): Binary content of Excel input file containing sheets:
            - {crop}: Demand profile data with Timestep, Outside Temp, Heat Demand,
              Cold Demand, and Elec Demand columns.
            - "Prices": Energy price data with Gas Price and Elec Price columns.
            - "Params": System parameters with Asset, Parameter, and Value columns.
            - "Settings": Global settings with Parameter and Value columns.
        crop (str, optional): Crop type identifier matching a sheet name.
            Defaults to "Tomaat".
        years (int, optional): Number of years to replicate data for. Defaults to 1.
        target_heat_demand_gwh (float, optional): Scale demand profiles to match
            target annual heat demand in GWh. If None, uses "Total_heat_demand"
            from Settings sheet.

    Returns:
        tuple: A tuple containing:
            - demand_profiles (dict): Dict with keys ["Outside Temp", "Heat Demand",
              "Cold Demand", "Elec Demand"] mapping to hourly numpy arrays.
            - energy_prices (dict): Dict with keys ["Gas Price", "Elec Price"]
              mapping to hourly numpy arrays.
            - n_hours (int): Total number of simulation hours.
            - params_from_excel (dict): Nested dict with asset names as keys
              and parameter dicts as values.
            - local_settings (dict): Global settings from Settings sheet.
            - timesteps (pd.Series): Datetime index for each hour.
    """
    xls = BytesIO(file_content)
    sheets = pd.read_excel(xls, sheet_name=[crop, "Prices", "Params", "Settings"])
    df_demand = sheets[crop]
    df_prices = sheets["Prices"]
    df_params = sheets["Params"]
    df_settings = sheets["Settings"]

    df_demand["Timestep"] = pd.to_datetime(df_demand["Timestep"], errors="coerce")
    local_settings = df_settings.set_index("Parameter")["Value"].to_dict()

    target_heat_demand = target_heat_demand_gwh if target_heat_demand_gwh is not None else local_settings.get("Total_heat_demand")
    if target_heat_demand is not None and not pd.isna(target_heat_demand):
        target_heat_demand_wh = target_heat_demand * 10**6
        current_heat_demand = df_demand["Heat Demand"].sum()

        if current_heat_demand > 0:
            scale_factor = target_heat_demand_wh / current_heat_demand
            df_demand["Heat Demand"] *= scale_factor
            df_demand["Cold Demand"] *= scale_factor
            df_demand["Elec Demand"] *= scale_factor

    params_from_excel = {
        group: df.set_index("Parameter")["Value"].to_dict()
        for group, df in df_params.groupby("Asset")
    }

    demand_profiles = {col: df_demand[col].to_numpy() for col in ["Outside Temp", "Heat Demand", "Cold Demand", "Elec Demand"]}
    energy_prices = {col: df_prices[col].to_numpy() for col in ["Gas Price", "Elec Price"]}

    demand_profiles = {k: np.tile(v, years) for k, v in demand_profiles.items()}
    energy_prices = {k: np.tile(v, years) for k, v in energy_prices.items()}

    if df_demand["Timestep"].notna().all():
        timesteps = pd.concat(
            [df_demand["Timestep"] + pd.DateOffset(years=i) for i in range(years)],
            ignore_index=True,
        )
    else:
        timesteps = pd.Series(pd.date_range(start="2000-01-01", periods=len(demand_profiles["Heat Demand"]), freq="h"))

    n_hours = len(demand_profiles["Heat Demand"])
    return demand_profiles, energy_prices, n_hours, params_from_excel, local_settings, timesteps


def list_crop_sheets(file_content: bytes):
    """List available crop types from Excel input file.

    Extracts sheet names from the Excel file, excluding system/config sheets
    to identify available crop types that can be used as demand profiles.

    Args:
        file_content (bytes): Binary content of Excel input file.

    Returns:
        list: Sheet names representing available crops, excluding system sheets
            ("Params", "Settings", "Results", "ATES", "Prices", "Guide").
    """
