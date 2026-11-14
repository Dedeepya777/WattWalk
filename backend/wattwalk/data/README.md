# Data Adapters Documentation (Person 1)

This module provides data access layers for WattWalk:
- `matterport.py`: Matterport GraphQL Model API for room geometry, polygons, panos, walls, and skybox face images.
- `index.py`: Index loader for the hackathon models index (`fixtures/models_index.csv`).
- `costar.py`: CoStar data kit join.
- `ebewe.py`: City of Los Angeles Existing Buildings Energy & Water Efficiency (EBEWE) program public Socrata API.
- `vexcel.py`: Vexcel aerial imagery extract endpoint (`/v2/ortho/extract`) and roof attributes.
- `building.py`: Composite Building context aggregator.
- `probes.py`: Integration health probes for Matterport, EBEWE, CoStar kit, and Vexcel.

## CoStar Column Mapping (Section 13.2, U4)

CoStar records join by `costar_property_id` or `homes_listing_id`. Mapped fields:
- `year_built`: matched against `year_built`, `built_year`, or `built`
- `units`: matched against `units`, `unit_count`, or `total_units`
- `asking_rent_usd_month`: matched against `rent`, `asking_rent`, or `asking`
- `unit_floor_area_m2`: matched against `area`, `sqft`, or `gfa` (converted from sqft to m2 via factor 0.092903 if sqft > 500)

## Vexcel Roof Attributes (Section 13.4, U5, P1-3)

- **Ortho Extract**: `POST https://api.vexcelgroup.com/v2/ortho/extract` with body parameters `wkt`, `srid: 4326`, `layer: "urban,urban-r,wide-area,urban-g"`, `crop: "bounding_box"`, `image-format: "jpeg"`, `destination-dimensions: "1400,1400"`, `attribution: "false"`.
- **Roof Attributes Finding**: The Vexcel hackathon API keys only authorize access to the ortho extract endpoint in Houston and Los Angeles (HTTP 403 outside). No parcel or roof attribute endpoint is authorized for the hackathon key tier. `roof_attributes(lat, lon)` logs `"Vexcel roof attributes endpoint not available to hackathon keys"` and returns `None` (empty `{}` in fixture mode).

## LA EBEWE Socrata Normalization (Section 13.3)

Street address normalization:
- Uppercase
- First comma-separated component
- Periods and unit indicators (`APT`, `UNIT`, `STE`, `#`) stripped
- Street types abbreviated (`STREET` -> `ST`, `AVENUE` -> `AVE`, `BOULEVARD` -> `BLVD`, etc.)
- Single quotes doubled for Socrata SoQL escaping

## Sourced Assumptions Table (P1-7)

| Key | Old Value | New Value | Source |
| :--- | :--- | :--- | :--- |
| `electricity_rate_usd_per_kwh` | LA: 0.30, HOU: 0.15 | LA: 0.30, HOU: 0.15 | LADWP Electric Rates Ordinance (Rate Schedule R-1) & EIA Electric Power Monthly table 5.6.A (TX avg ~$0.15/kWh), https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_06_a |
| `lighting_hours_per_day` | 3 | 3 | US DOE / ENERGY STAR Lighting Market Characterization & Building America benchmark (average 3.0 h/day), https://www.energy.gov/eere/buildings/building-america |
| `bulb_w_incandescent` | 60 | 60 | DOE Energy Conservation Standards for General Service Lamps, 10 CFR Part 430 (standard 60W A19 incandescent baseline delivering ~800 lumens), https://www.energy.gov/eere/buildings/appliance-and-equipment-standards-program |
| `bulb_w_led` | 9 | 9 | ENERGY STAR Program Requirements for Lamps Version 2.1 (9W LED equivalent delivering ~800 lumens), https://www.energystar.gov/products/lighting_fans/light_bulbs |
| `default_unit_floor_area_m2` | 70 | 70 | US Census Bureau, Survey of Construction (SOC) median multifamily apartment square footage (~750 sq ft / 70 m2), https://www.census.gov/construction/chars/ |
| `cooling_kwh_per_m2_yr` | LA: 30/22/15, HOU: 70/55/40 | LA: 30/22/15, HOU: 70/55/40 | EIA Residential Energy Consumption Survey (RECS) Table CE5.2 Household Electricity End-Use Consumption by Climate Zone & Vintage, https://www.eia.gov/consumption/residential/data/2020/ |
| `window_solar_cooling_kwh_per_m2_yr` | LA: 60, HOU: 110 | LA: 60, HOU: 110 | NREL / DOE Building America National Benchmark Definition (cooling load attributable to window solar heat gain in IECC climate zones 3B & 2A), https://www.nrel.gov/docs/fy10osti/47246.pdf |
| `window_film_reduction` | 0.30 | 0.30 | US DOE Energy Saver, Window Treatments and Coverings (solar control films reduce solar heat gain coefficient SHGC by 25-35%), https://www.energy.gov/energysaver/window-treatments-and-coverings |
| `eer_window_ac_old` | 9.0 | 9.0 | DOE Appliance Standards 10 CFR § 430.32(b) for Room Air Conditioners manufactured prior to 2014 (standard minimum EER 9.0), https://www.energy.gov/eere/buildings/appliance-and-equipment-standards-program |
| `eer_heat_pump_new` | 18.0 | 18.0 | ENERGY STAR Program Requirements for Air-Source Heat Pumps Version 6.0 / Most Efficient criteria (SEER/EER 18+), https://www.energystar.gov/products/most_efficient |
| `thermostat_hvac_savings_fraction` | 0.08 | 0.08 | EPA ENERGY STAR Connected Thermostat field study summary (documented ~8% average cooling energy reduction in residential field evaluations), https://www.energystar.gov/products/heating_cooling/connected_thermostats |
| `fridge_kwh_yr_old` | 700 | 700 | ENERGY STAR Flip Your Fridge Calculator (typical pre-2001 standard top/bottom refrigerator consumes ~700-800 kWh/yr), https://www.energystar.gov/products/appliances/refrigerators/flip-the-fridge-calculator |
| `fridge_kwh_yr_new` | 400 | 400 | ENERGY STAR Certified Refrigerator Product Specification Version 5.1 (standard ~18-20 cu. ft. unit consumes ~350-400 kWh/yr), https://www.energystar.gov/products/appliances/refrigerators |
| `default_room_height_m` | 2.6 | 2.6 | International Residential Code (IRC) Section R305 Ceiling Height standard (standard 8 ft 6 in / 2.6 m), https://codes.iccsafe.org |
| `kbtu_per_ft2_to_kwh_per_m2` | 3.15459 | 3.15459 | Physical constant: 1 kBtu = 0.293071 kWh; 1 ft2 = 0.092903 m2; NIST Special Publication 811, https://www.nist.gov/pml/special-publication-811 |
