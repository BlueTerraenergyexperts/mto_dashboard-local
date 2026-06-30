# MTO Dashboard - Greenhouse Horticulture Thermal Energy Storage Simulator

A Python-based Streamlit application for simulating and analyzing aquifer thermal energy storage (ATES) systems combined with various heating/cooling technologies for greenhouse horticulture energy supply.

## Overview

The MTO Dashboard provides a comprehensive simulation environment for analyzing the performance of greenhouse energy systems that incorporate:

- **Aquifer Thermal Energy Storage (ATES)** - Seasonal storage with hot and cold wells
- **Geothermal Heat** - Direct geothermal energy supply for greenhouse heating
- **Combined Heat & Power (CHP)** - Gas-fired power generation with heat recovery for process heat and electricity
- **Heat Pumps** - Condenser and electric boiler units for additional capacity
- **Thermal Buffers** - Short-term thermal storage to manage peak horticulture heating and cooling demands
- **Gas Boilers** - Backup heating capacity

The simulator uses hourly time-step calculations with detailed aquifer thermal models including fluid transport advection and conduction losses, optimized with Numba JIT compilation for performance.

## Features

- **Interactive Dashboard UI** - Streamlit-based interface for scenario configuration and visualization
- **Flexible Input Configuration** - Excel-based parameter input with support for multiple greenhouse crop types
- **Hourly Simulation** - Accurate year-round or multi-year energy balance calculations for greenhouse heating and cooling
- **Advanced ATES Modeling** - Mesh-based aquifer thermal model with temperature tracking
- **Technology Integration** - Automatic dispatch of heating/cooling technologies based on energy prices and crop demand
- **Performance Analytics** - KPIs for efficiency, costs, and energy flows
- **Data Visualization** - Interactive plots of hourly and daily energy generation
- **Scenario Caching** - Fast re-execution of previously run scenarios

## Project Structure

```
MTO_model_2026_local/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── dashboard.py                       # Streamlit UI application
├── control_panel.py                   # Simulation orchestration
├── calculation_model.py                # Core physics models
│   ├── Tech                           # Individual technology class
│   ├── ATESModel                      # Single ATES well model
│   └── ATESDoublet                    # Paired hot/cold ATES system
├── input_processing.py                # Excel input parsing & data preparation
├── output_generation.py               # Results aggregation and KPI calculation
└── MTO_model_input_opleverversie.xlsx # Example input configuration
```

## Installation

### Requirements

- Python 3.9 or higher
- Virtual environment manager (venv, conda, or similar)

### Setup Steps

1. **Clone or download the project**
   ```bash
   cd MTO_model_2026_local
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Running the Dashboard

Start the Streamlit application:

```bash
streamlit run dashboard.py
```

The dashboard will open in your default web browser at `http://localhost:8501`

### Input File Format

The application accepts Excel files (.xlsx) with the following structure:

**Required Sheets:**
- Technology parameters (Geothermal, CHP, MTS, Buffer, Eboiler, Gasboiler, Condenser)
- Demand profiles for various crops/usage types
- Energy price time series (electricity and gas)
- ATES system configuration

See `MTO_model_input_opleverversie.xlsx` for the required format.

### Configuration Parameters

#### System Settings
- **Years of simulation** - 1-5 years (hourly resolution)
- **Flow mode** - "High Flow" or standard flow for ATES system
- **Well temperatures** - Hot well setpoint (°C) and cold well setpoint (°C)

#### Technology Overrides
- **Geothermal Power** - Override thermal power capacity (MW)
- **CHP Power** - Override CHP thermal power capacity (MW)
- **Target Heat Demand** - Scale demand profile to target annual supply (GWh)
- **MTS Flow Limit** - Override ATES flow rate (m³/h)

### Interpreting Results

**KPIs Displayed:**
- **Totale warmtevraag** - Total annual heat demand (GWh)
- **Verplaatste GWh** - Heat supplied by ATES system (GWh)
- **MTO efficiency** - Roundtrip efficiency of ATES storage
- **Elektriciteitsgebruik** - Total electricity for heat pumps (GWh)
- **Rekentijd** - Simulation runtime (seconds)
- **nr_doubletten** - Number of ATES well-pairs deployed

**Output Visualizations:**
- Hourly heat generation by technology
- Daily aggregated energy supply
- ATES well temperature evolution over time
- Technology deployment and utilization

## Core Modules

### calculation_model.py

Implements the physics models:

- **Tech class** - Represents individual heating/cooling technologies
  - Power availability calculations based on prices
  - Technology-specific deployment logic
  
- **ATESModel class** - Single aquifer well simulation
  - Mesh-based temperature tracking (61,100 elements)
  - Fluid transport advection
  - Thermal conduction between layers
  - Optimized with Numba JIT compilation
  
- **ATESDoublet class** - Paired hot/cold well system
  - Coordinated charging and discharging
  - Temperature recovery between wells
  
- **run_simulation()** - Main hourly simulation loop
  - Technology dispatch sequencing
  - Energy balance tracking
  - Progress reporting

### input_processing.py

Data preparation and input handling:

- Excel file parsing with openpyxl
- Time series construction for hourly demands and prices
- Demand profile scaling by crop type
- Technology parameter extraction and validation

### output_generation.py

Results generation and analysis:

- **build_results_frame()** - Aggregates hourly simulation outputs
- **build_kpis()** - Calculates key performance indicators
- **build_daily_output()** - Resamples to daily energy totals

### dashboard.py

Streamlit UI with:

- File upload and scenario configuration
- Parameter adjustment interface
- Real-time progress tracking
- Interactive visualizations
- Scenario caching for performance

## System Architecture

### Simulation Workflow

```
1. Load Excel Configuration
   ↓
2. Parse Input Parameters & Time Series
   ↓
3. Initialize ATES Doublet & All Technologies
   ↓
4. Calculate Technology Available Power (hourly)
   ↓
5. Run Hourly Simulation Loop:
   - Apply technologies in sequence (Geothermal → Eboiler → CHP → Buffer → Condenser → MTS → Gasboiler)
   - Update residual demand
   - Track energy flows
   - Update ATES well temperatures
   ↓
6. Generate Results & KPIs
   ↓
7. Display Results & Visualizations
```

### ATES Modeling Details

The aquifer thermal model uses:

- **Mesh-based approach** - 61,100 elements representing aquifer volume
- **Bucket aggregation** - Size-dependent buckets for computational efficiency
- **Advection** - Fluid transport through aquifer mesh
- **Conduction** - Heat diffusion between mesh elements and surroundings
- **Internal time stepping** - Sub-hourly steps (typically 20-30 per hour) for stability
- **Numba optimization** - JIT-compiled critical loops for 10-50x speedup

## Performance Considerations

- **Simulation time** - Typically 60-90 seconds per year depending on system complexity
- **Memory usage** - ~500 MB for 5-year simulations
- **Caching** - Identical scenarios use cached results for instant retrieval
- **Numba requirement** - Significant speedup with Numba; falls back to pure Python if unavailable

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| numpy | 2.1.3 | Numerical arrays and computations |
| pandas | 2.2.3 | Data manipulation and analysis |
| streamlit | 1.53.0 | Web application framework |
| plotly | 5.24.1 | Interactive visualizations |
| openpyxl | 3.1.5 | Excel file reading/writing |
| numba | 0.61.0 | JIT compilation for performance |
| xlrd | (latest) | Legacy Excel support |

## Development

### Adding New Technologies

1. Define a new Tech instance in `initialize_techs()` in calculation_model.py
2. Implement a `calc_*_available_power()` method for the technology
3. Add the technology to the dispatch sequence in `run_simulation()`
4. Update output_generation.py to include the technology in results

### Extending Input Parameters

1. Add new sheets or columns to the input Excel file
2. Parse new parameters in `input_processing.py`
3. Pass parameters to technology objects in `control_panel.py`

### Customizing the UI

Modify dashboard.py to add new controls, visualization, or analysis sections.

## Troubleshooting

### Common Issues

**ImportError: No module named 'numba'**
- Solution: Install numba via `pip install numba`
- The simulator will work without it but will be slower

**ValueError: Crop type not found**
- Ensure the Excel file contains sheets/data for the selected crop type
- Check crop names match those in the input file

**MemoryError with large simulations**
- Reduce simulation years or increase system memory
- Consider splitting into multiple smaller simulations

**Streamlit cache issues**
- Clear cache: Delete `.streamlit/cache` directory
- Restart the Streamlit app

## License

[License information to be added]

## Contributing

[Contribution guidelines to be added]

## Support & Contact

- **Author** - Jeroen Larrivee
- **Company** - BlueTerra
- **Website** - https://blueterra.nl
- **GitHub** - https://github.com/Jlar01/mto_dashboard-local

## References & Background

### Aquifer Thermal Energy Storage (ATES)

ATES systems store thermal energy in aquifers for seasonal energy recovery. This model simulates:
- Groundwater flow and transport
- Temperature mixing and diffusion
- Well-pair coordination (hot/cold)
- Thermal losses through conduction

### Greenhouse Horticulture Energy Management

Integrated greenhouse energy systems optimize renewable heat sources, seasonal thermal storage, and supplementary generation to support stable crop climate control and lower operating costs.

## Changelog

### Version 0.2.1
- Added comprehensive docstrings to all modules
- Created detailed README documentation
- Enhanced error handling and validation

### Version 0.2.0
- Initial release with Streamlit dashboard
- ATES doublet modeling with Numba optimization
- Multi-technology dispatch simulation

---

**Last Updated**: June 2026
