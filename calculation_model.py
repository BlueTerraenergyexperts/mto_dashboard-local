import warnings
from math import pi

import numpy as np

warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

    def njit(*_args, **_kwargs):
        def decorator(func):
            return func
        return decorator


class Tech:
    def __init__(self, name, n_hours, **kwargs):
        self.name = name
        self.N_hours = n_hours
        self.available_power = np.zeros(n_hours)
        self.direct_use = np.zeros(n_hours)
        self.residual = np.zeros(n_hours)
        for k, v in kwargs.items():
            setattr(self, k, v)

    def _require(self, *attrs):
        for a in attrs:
            if not hasattr(self, a) or getattr(self, a) is None:
                raise ValueError(f"{a} must be defined before calculation.")

    def _set_constant_power(self):
        self._require("thermal_power")
        self.available_power[:] = self.thermal_power

    def calc_condenser_available_power(self, prices, cold_demand, outside_temp, geo_price):
        self._require("COP_upgrading", "Carnot")
        self.COP_nupg = self.Carnot * (14 + 273) / np.maximum(1, (outside_temp + 12) - 14)
        self.deployment_price = prices["Elec Price"] * ((1 / (self.COP_upgrading + 1)) - (1 / self.COP_nupg))
        self.deployment = self.deployment_price <= geo_price
        self.COP = self.deployment * self.COP_upgrading + np.logical_not(self.deployment) * self.COP_nupg
        self.electricity_use = self.deployment * (cold_demand / self.COP_upgrading)
        self.available_power = self.deployment * (cold_demand + self.electricity_use)

    def calc_chp_available_power(self, prices, geo_price):
        self._require("thermal_efficiency", "electrical_efficiency", "thermal_power", "maintenance_costs")
        self.deployment_price = (
            (prices["Gas Price"] - geo_price * self.thermal_efficiency) / self.electrical_efficiency
            + self.maintenance_costs
        )
        self.deployment = prices["Elec Price"] >= self.deployment_price
        self.available_power = self.deployment * self.thermal_power

    def calc_geothermal_available_power(self):
        self._set_constant_power()

    def calc_eboiler_available_power(self, prices):
        self._require("thermal_power", "deployment_price")
        self.deployment = prices["Elec Price"] <= self.deployment_price
        self.available_power = self.deployment * self.thermal_power

    def calc_gasboiler_power(self):
        self._set_constant_power()

    def apply_tech(self, t, demand_profiles):
        col_name = f"Residual Heat Demand after {self.name}"
        demand_profiles.setdefault(col_name, np.zeros_like(demand_profiles["Heat Demand"]))

        prev = demand_profiles["Residual Heat Demand"][t]
        demand_profiles["Previous Residual Heat Demand"][t] = prev

        new_residual = max(prev - self.available_power[t], 0)
        demand_profiles["Residual Heat Demand"][t] = new_residual

        self.direct_use[t] = prev - new_residual
        self.residual[t] = self.available_power[t] - self.direct_use[t]
        demand_profiles[col_name][t] = new_residual

    def apply_buffer(self, t, demand_profiles, techs, buff_tech_list=None):
        if buff_tech_list is None:
            buff_tech_list = []

        hourly_loss_factor = -0.0008
        if t:
            self.losses[t] = hourly_loss_factor * (self.charge[t - 1] + self.charging[t - 1] - self.discharging[t - 1])
            self.charge[t] = (self.charge[t - 1] + self.charging[t - 1] - self.discharging[t - 1]) - self.losses[t]

        self.available_power[t] = min(self.power, self.charge[t])
        self.apply_tech(t, demand_profiles)
        self.discharging[t] = self.direct_use[t]

        for buff_tech in buff_tech_list:
            available = techs[buff_tech].residual[t]
            to_buffer = min(available, self.power - self.charging[t], self.capacity - self.charge[t] - self.charging[t])
            techs[buff_tech].to_buffer[t] = to_buffer
            techs[buff_tech].residual[t] -= to_buffer
            self.charging[t] += to_buffer

    def apply_MTS(self, t, demand_profiles, energy_prices, temp_cold_well, techs, ates, model_settings, buff_tech_list=None):
        if buff_tech_list is None:
            buff_tech_list = ("Condenser", "Geothermal")

        if t:
            t_hot_last = ates.last_hot_temp()
            if t_hot_last > temp_cold_well:
                gasprijs = 45
                local_delta_t = t_hot_last - ates.cold.T_in
                self.COP[t] = self.Carnot * (model_settings["Temp_heating"] + 273) / (
                    model_settings["Temp_heating"] - (0.5 * (t_hot_last + ates.cold.T_in))
                )

                loc_available_power = (
                    self.flow_limit
                    * self.nr_doubletten
                    * (local_delta_t * ates.hot.C_w)
                    / (3.6 * 10**6)
                    * (1 + 1 / self.COP[t])
                )

                pump_head = 600000
                eta_pump = 0.6
                self.pump_electricity_use_per_heat[t] = (
                    pump_head / (eta_pump * local_delta_t * ates.hot.C_w) * (self.COP[t] / (1 + self.COP[t]))
                )
                self.price[t] = energy_prices["Elec Price"][t] * (1 / self.COP[t] + self.pump_electricity_use_per_heat[t])

                if self.price[t] < gasprijs:
                    self.available_power[t] = loc_available_power

        self.apply_tech(t, demand_profiles)
        self.discharging[t] = self.direct_use[t]

        if t:
            local_delta_t_charging = ates.hot.T_in - ates.last_cold_temp()
        else:
            local_delta_t_charging = ates.hot.T_in - ates.hot.T_amb

        for buff_tech in buff_tech_list:
            available = techs[buff_tech].residual[t]
            to_mts_t = min(
                available,
                self.flow_limit * self.nr_doubletten * (local_delta_t_charging * ates.hot.C_w) / (3.6 * 10**6)
                - self.charging[t],
            )

            techs[buff_tech].to_MTS[t] = to_mts_t
            techs[buff_tech].residual[t] -= to_mts_t
            self.charging[t] += to_mts_t

        if self.direct_use[t] != 0:
            self.electricity_use[t] = self.direct_use[t] * (self.pump_electricity_use_per_heat[t] + 1 / self.COP[t])
            self.electricity_cost[t] = self.electricity_use[t] * energy_prices["Elec Price"][t] / 1000

        net_charging = self.charging[t] - self.discharging[t] * (1 - 1 / (1 + self.COP[t]))
        net_charging_per_doublet = net_charging / self.nr_doubletten
        _, _, flowratehot, _ = ates.step((net_charging_per_doublet) * 3.6 * 10**6)
        self.m3_flow[t] = flowratehot


def initialize_techs(n_hours, excel_params):
    tech_names = ["Condenser", "Geothermal", "CHP", "Eboiler", "Buffer", "MTS", "Gasboiler"]
    techs = {name: Tech(name, n_hours) for name in tech_names}

    hourly_fields = {
        "Condenser": ["to_MTS", "electricity_use", "COP", "to_buffer"],
        "CHP": ["to_buffer", "to_MTS"],
        "Geothermal": ["to_MTS", "to_buffer"],
        "Eboiler": ["to_buffer", "to_MTS"],
        "Buffer": ["charging", "discharging", "charge", "losses"],
        "MTS": [
            "charging",
            "discharging",
            "electricity_use",
            "COP",
            "price",
            "electricity_cost",
            "m3_flow",
            "pump_electricity_use_per_heat",
        ],
        "Gasboiler": [],
    }

    for name in tech_names:
        if name in excel_params:
            for k, v in excel_params[name].items():
                setattr(techs[name], k, v)

        for field in hourly_fields.get(name, []):
            setattr(techs[name], field, np.zeros(n_hours))

        if not hasattr(techs[name], "thermal_power"):
            if hasattr(techs[name], "power") and hasattr(techs[name], "thermal_efficiency"):
                techs[name].thermal_power = techs[name].power * techs[name].thermal_efficiency

        if name == "Gasboiler" and not hasattr(techs[name], "thermal_power"):
            techs[name].thermal_power = 20000.0

    if "Buffer" in techs and hasattr(techs["Buffer"], "capacity"):
        techs["Buffer"].charge[0] = 0.5 * techs["Buffer"].capacity

    return techs


def prep(t, t_prev, t_curr):
    if t != 1:
        t_prev, t_curr = t_curr, t_prev
    return t_prev, t_curr


def compute_flow_rate(heat, delta_t, dt, c_w, v_in_cum):
    if heat != 0:
        f_in = heat / (c_w * delta_t)
        f_in_timestep = f_in * dt / 3600
        v_in_cum += f_in_timestep
        return v_in_cum, f_in
    return v_in_cum, 0


def flux_and_retard(v_in_cum, v_mesh, t_prev, t_in, t_amb, c_s_weighted, c_w_weighted, c_aq_inv, n_mesh):
    if v_in_cum >= v_mesh:
        v_in = int(v_in_cum // v_mesh)
        v_in_cum -= v_in * v_mesh
        t_prev[v_in:] = (c_s_weighted * t_prev[v_in:] + c_w_weighted * t_prev[:-v_in]) * c_aq_inv
        t_prev[:v_in] = (c_s_weighted * t_prev[:v_in] + c_w_weighted * t_in) * c_aq_inv
        n_mesh += v_in

    if v_in_cum <= -v_mesh:
        v_out = int(v_in_cum // -v_mesh)
        v_in_cum -= v_out * -v_mesh
        t_prev[:-v_out] = (c_s_weighted * t_prev[:-v_out] + c_w_weighted * t_prev[v_out:]) * c_aq_inv
        t_prev[-v_out:] = (c_s_weighted * t_prev[-v_out:] + c_w_weighted * t_amb) * c_aq_inv

    return t_prev, v_in_cum, n_mesh


def update_temperatures(t_prev, t_curr, n_mesh, t_amb, dt, inv_cap, bucket_map, g_con, q_in, q_out):
    bucket_ranges = [(0, 100, 1), (100, 1100, 10), (1100, 11100, 100), (11100, 61100, 1000)]
    t_avg = np.concatenate([t_prev[s:e].reshape(-1, n).mean(1) for (s, e, n) in bucket_ranges])
    t_avg[t_avg <= t_amb + 0.01] = t_amb

    q_between = g_con * (t_avg[:-1] - t_avg[1:])
    q_in[1:], q_out[:-1] = q_between, q_between
    dt_arr = (q_in - q_out) * dt * inv_cap

    t_curr[:n_mesh] = t_prev[:n_mesh]
    t_curr[:n_mesh] += dt_arr[bucket_map][:n_mesh]
    return t_curr, t_avg


@njit(cache=True)
def prep_nb(t, t_prev, t_curr):
    if t != 1:
        return t_curr, t_prev
    return t_prev, t_curr


@njit(cache=True)
def compute_flow_rate_nb(heat, delta_t, dt, c_w, v_in_cum):
    if heat != 0.0:
        f_in = heat / (c_w * delta_t)
        f_in_timestep = f_in * dt / 3600.0
        v_in_cum += f_in_timestep
    else:
        f_in = 0.0

    return v_in_cum, f_in


@njit(cache=True)
def flux_and_retard_nb(v_in_cum, v_mesh, t_prev, t_in, t_amb, c_s_weighted, c_w_weighted, c_aq_inv, n_mesh):
    if v_in_cum >= v_mesh:
        v_in = int(v_in_cum // v_mesh)
        v_in_cum -= v_in * v_mesh

        for i in range(t_prev.size - 1, v_in - 1, -1):
            t_prev[i] = (c_s_weighted * t_prev[i] + c_w_weighted * t_prev[i - v_in]) * c_aq_inv

        for i in range(v_in):
            t_prev[i] = (c_s_weighted * t_prev[i] + c_w_weighted * t_in) * c_aq_inv

        n_mesh += v_in

    if v_in_cum <= -v_mesh:
        v_out = int(v_in_cum // -v_mesh)
        v_in_cum += v_out * v_mesh

        for i in range(t_prev.size - v_out):
            t_prev[i] = (c_s_weighted * t_prev[i] + c_w_weighted * t_prev[i + v_out]) * c_aq_inv

        for i in range(t_prev.size - v_out, t_prev.size):
            t_prev[i] = (c_s_weighted * t_prev[i] + c_w_weighted * t_amb) * c_aq_inv

    return t_prev, v_in_cum, n_mesh


@njit(cache=True)
def update_temperatures_nb(
    t_prev,
    t_curr,
    n_mesh,
    t_amb,
    dt,
    inv_cap,
    bucket_map,
    bucket_starts,
    bucket_sizes,
    g_con,
    q_in,
    q_out,
    dt_arr,
    t_avg,
):
    floor_temp = t_amb + 0.01

    for b in range(t_avg.size):
        start = bucket_starts[b]
        size = bucket_sizes[b]
        s = 0.0
        for j in range(start, start + size):
            s += t_prev[j]
        avg = s / size
        if avg <= floor_temp:
            avg = t_amb
        t_avg[b] = avg

    q_in[0] = 0.0
    q_out[t_avg.size - 1] = 0.0

    for i in range(t_avg.size - 1):
        q = g_con[i] * (t_avg[i] - t_avg[i + 1])
        q_out[i] = q
        q_in[i + 1] = q

    for b in range(t_avg.size):
        dt_arr[b] = (q_in[b] - q_out[b]) * dt * inv_cap[b]

    for i in range(n_mesh):
        t_curr[i] = t_prev[i] + dt_arr[bucket_map[i]]

    return t_curr, t_avg


@njit(cache=True)
def ates_step_nb(
    heat,
    delta_t,
    t_prev,
    t_curr,
    t_avg,
    v_in_cum,
    n_mesh,
    n_internal_steps,
    dt,
    c_w,
    v_mesh,
    t_in,
    t_amb,
    c_s_weighted,
    c_w_weighted,
    c_aq_inv,
    inv_cap,
    bucket_map,
    bucket_starts,
    bucket_sizes,
    g_con,
    q_in,
    q_out,
    dt_arr,
):
    flowrate = 0.0

    for internal_t in range(n_internal_steps):
        t_prev, t_curr = prep_nb(internal_t, t_prev, t_curr)
        v_in_cum, flowrate = compute_flow_rate_nb(heat, delta_t, dt, c_w, v_in_cum)
        t_prev, v_in_cum, n_mesh = flux_and_retard_nb(
            v_in_cum,
            v_mesh,
            t_prev,
            t_in,
            t_amb,
            c_s_weighted,
            c_w_weighted,
            c_aq_inv,
            n_mesh,
        )
        t_curr, t_avg = update_temperatures_nb(
            t_prev,
            t_curr,
            n_mesh,
            t_amb,
            dt,
            inv_cap,
            bucket_map,
            bucket_starts,
            bucket_sizes,
            g_con,
            q_in,
            q_out,
            dt_arr,
            t_avg,
        )


    return t_prev, t_curr, t_avg, v_in_cum, n_mesh, flowrate


class ATESModel:
    def __init__(self, factor, t_in, t_in_hot, t_initial=None):
        self.factor = factor
        self.flowrate = 0

        self.k_aq = factor * 2.55
        self.phi = 0.3
        rho_w, rho_s = 1000, 2640
        c_w, c_s = 4200, 710

        self.C_w = rho_w * c_w
        self.C_s = rho_s * c_s
        self.C_s_weighted = (1 - self.phi) * self.C_s
        self.C_w_weighted = self.phi * self.C_w

        self.C_aq = self.C_s_weighted + self.C_w_weighted
        self.C_aq_inv = 1.0 / self.C_aq

        self.H = 30
        self.T_amb = 12
        self.T_hot = t_in_hot
        self.T_in = t_in

        self.N_mesh_max = 61100
        self.V_mesh = 15

        self.N_mesh = 350
        self.V_mesh_array = np.zeros(self.N_mesh)
        self.V_mesh_array[:100] = 1 * self.V_mesh
        self.V_mesh_array[100:200] = 10 * self.V_mesh
        self.V_mesh_array[200:300] = 100 * self.V_mesh
        self.V_mesh_array[300:350] = 1000 * self.V_mesh

        combined = np.r_[0.5:100:1, 105:1100:10, 1150:11100:100, 11600:61100:1000]
        self.radii = np.sqrt(combined * self.V_mesh / (pi * self.H))
        self.G_con = 2 * pi * self.H * self.k_aq / np.log(self.radii[1:] / self.radii[:-1])

        self.bucket_sizes = (self.V_mesh_array / self.V_mesh).astype(np.int64)
        self.bucket_starts = np.empty(self.N_mesh, dtype=np.int64)
        start = 0
        for b in range(self.N_mesh):
            self.bucket_starts[b] = start
            start += self.bucket_sizes[b]
        self.bucket_map = np.repeat(np.arange(len(self.bucket_sizes)), self.bucket_sizes)
        self.inv_cap = 1.0 / (self.V_mesh_array * self.C_aq)

        self.q_in = np.zeros(len(self.radii))
        self.q_out = np.zeros(len(self.radii))
        self.dt_arr = np.zeros(self.N_mesh)

        self.dt = 180 / factor
        self.n_internal_steps = int(3600 / self.dt)

        self.reset_state(t_initial)

    def reset_state(self, t_initial=None):
        if t_initial is None:
            self.T_prev = np.ones(self.N_mesh_max) * self.T_amb
            self.T_curr = np.ones(self.N_mesh_max) * self.T_amb
        else:
            t_arr = np.asarray(t_initial)
            if t_arr.shape[0] != self.N_mesh_max:
                raise ValueError(f"T_initial must have length {self.N_mesh_max}.")
            self.T_prev = t_arr.copy()
            self.T_curr = t_arr.copy()

        self.T_avg = np.zeros(self.N_mesh)
        for b in range(self.N_mesh):
            mask = self.bucket_map == b
            self.T_avg[b] = self.T_curr[mask].mean()

        self.V_in_cum = 0.0

    def step(self, heat, delta_t):
        if NUMBA_AVAILABLE and delta_t is not None:
            self.T_prev, self.T_curr, self.T_avg, self.V_in_cum, self.N_mesh, self.flowrate = ates_step_nb(
                heat,
                delta_t,
                self.T_prev,
                self.T_curr,
                self.T_avg,
                self.V_in_cum,
                self.N_mesh,
                self.n_internal_steps,
                self.dt,
                self.C_w,
                self.V_mesh,
                self.T_in,
                self.T_amb,
                self.C_s_weighted,
                self.C_w_weighted,
                self.C_aq_inv,
                self.inv_cap,
                self.bucket_map,
                self.bucket_starts,
                self.bucket_sizes,
                self.G_con,
                self.q_in,
                self.q_out,
                self.dt_arr,
            )
            return self.T_curr, self.V_in_cum, self.flowrate

        for internal_t in range(self.n_internal_steps):
            self.T_prev, self.T_curr = prep(internal_t, self.T_prev, self.T_curr)
            self.V_in_cum, self.flowrate = compute_flow_rate(heat, delta_t, self.dt, self.C_w, self.V_in_cum)
            self.T_prev, self.V_in_cum, self.N_mesh = flux_and_retard(
                self.V_in_cum,
                self.V_mesh,
                self.T_prev,
                self.T_in,
                self.T_amb,
                self.C_s_weighted,
                self.C_w_weighted,
                self.C_aq_inv,
                self.N_mesh,
            )
            self.T_curr, self.T_avg = update_temperatures(
                self.T_prev,
                self.T_curr,
                self.N_mesh,
                self.T_amb,
                self.dt,
                self.inv_cap,
                self.bucket_map,
                self.G_con,
                self.q_in,
                self.q_out,
            )

        return self.T_curr, self.V_in_cum, self.flowrate


class ATESDoublet:
    def __init__(self, factor=2, t_in_hot=50, t_in_cold=25, n_hours=None):
        self.hot = ATESModel(factor=factor, t_in=t_in_hot, t_in_hot=t_in_hot)
        self.cold = ATESModel(factor=factor, t_in=t_in_cold, t_in_hot=t_in_hot)

        self._n_hours = n_hours
        if n_hours is not None:
            self.T_hot_all = np.empty(n_hours)
            self.T_cold_all = np.empty(n_hours)
        else:
            self.T_hot_all = []
            self.T_cold_all = []
        self._step_index = 0

    def last_hot_temp(self):
        if self._step_index == 0:
            return self.hot.T_in
        if self._n_hours is not None:
            return self.T_hot_all[self._step_index - 1]
        return self.T_hot_all[-1]

    def last_cold_temp(self):
        if self._step_index == 0:
            return self.cold.T_in
        if self._n_hours is not None:
            return self.T_cold_all[self._step_index - 1]
        return self.T_cold_all[-1]

    def step(self, heat):
        if self._step_index == 0:
            if heat >= 0:
                delta_t = self.hot.T_in - self.cold.T_in
            else:
                raise ValueError("Can not discharge from hot well, isn't charged yet.")
        else:
            if heat > 0:
                delta_t = self.hot.T_in - self.last_cold_temp()
            elif heat < 0:
                delta_t = self.last_hot_temp() - self.cold.T_in
            else:
                delta_t = None

        t_out_hot, _, flowratehot = self.hot.step(heat, delta_t)
        t_out_cold, _, flowratecold = self.cold.step(-heat, delta_t)

        if self._n_hours is not None:
            self.T_hot_all[self._step_index] = t_out_hot[1]
            self.T_cold_all[self._step_index] = t_out_cold[1]
        else:
            self.T_hot_all.append(t_out_hot[1])
            self.T_cold_all.append(t_out_cold[1])
        self._step_index += 1
        return t_out_hot, t_out_cold, flowratehot, flowratecold


def run_simulation(n_hours, techs, demand_profiles, energy_prices, temp_cold_well, ates, model_settings, progress_callback=None):
    demand_profiles = {k: v.copy() for k, v in demand_profiles.items()}
    demand_profiles["Residual Heat Demand"] = demand_profiles["Heat Demand"].copy()
    demand_profiles["Previous Residual Heat Demand"] = demand_profiles["Residual Heat Demand"].copy()

    techs["Condenser"].calc_condenser_available_power(
        energy_prices,
        demand_profiles["Cold Demand"],
        demand_profiles["Outside Temp"],
        geo_price=techs["Geothermal"].price,
    )
    techs["CHP"].calc_chp_available_power(energy_prices, geo_price=techs["Geothermal"].price)
    techs["Geothermal"].calc_geothermal_available_power()
    techs["Eboiler"].calc_eboiler_available_power(energy_prices)
    techs["Gasboiler"].calc_gasboiler_power()

    if progress_callback is not None:
        progress_callback(0)

    last_progress = -1
    progress_step = max(1, n_hours // 100)

    for t in range(n_hours):
        for name in ["Geothermal", "Eboiler", "CHP", "Buffer", "Condenser", "MTS", "Gasboiler"]:
            if name == "Buffer":
                techs[name].apply_buffer(t, demand_profiles, techs=techs, buff_tech_list=["Eboiler", "CHP"])
            elif name == "MTS":
                techs[name].apply_MTS(
                    t,
                    demand_profiles,
                    energy_prices,
                    temp_cold_well,
                    techs=techs,
                    ates=ates,
                    model_settings=model_settings,
                    buff_tech_list=["Eboiler", "CHP", "Condenser", "Geothermal"],
                )
            else:
                techs[name].apply_tech(t, demand_profiles)

        if progress_callback is not None and (t % progress_step == 0 or t == n_hours - 1):
            progress = int(((t + 1) / n_hours) * 100)
            if progress != last_progress:
                progress_callback(progress)
                last_progress = progress

    return demand_profiles
