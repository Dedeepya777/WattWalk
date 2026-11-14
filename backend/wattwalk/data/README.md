# Data Adapters Documentation (Person 1)

This module provides data access layers for WattWalk:
- `matterport.py`: Matterport GraphQL Model API for room geometry, polygons, panos, walls, and skybox face images.
- `index.py`: Index loader for the hackathon models index (`fixtures/models_index.csv`).
- `costar.py`: CoStar data kit join.
- `ebewe.py`: City of Los Angeles Existing Buildings Energy & Water Efficiency (EBEWE) program public Socrata API.
- `vexcel.py`: Vexcel aerial imagery extract endpoint (`/v2/ortho/extract`) and roof attributes.
- `building.py`: Composite Building context aggregator.

## CoStar Column Mapping (Section 13.2, U4)

CoStar records join by `costar_property_id` or `homes_listing_id`. Mapped fields:
- `year_built`: matched against `year_built`, `built_year`, or `built`
- `units`: matched against `units`, `unit_count`, or `total_units`
- `asking_rent_usd_month`: matched against `rent`, `asking_rent`, or `asking`
- `unit_floor_area_m2`: matched against `area`, `sqft`, or `gfa` (converted from sqft to m2 via factor 0.092903 if sqft > 500)

## Vexcel Roof Attributes (Section 13.4, U5)

The Vexcel ortho aerial extractor extracts square bounding boxes centered on building latitude and longitude. Roof attributes fallback to `{}` when not provided by upstream.

## LA EBEWE Socrata Normalization (Section 13.3)

Street address normalization:
- Uppercase
- First comma-separated component
- Periods and unit indicators (`APT`, `UNIT`, `STE`, `#`) stripped
- Street types abbreviated (`STREET` -> `ST`, `AVENUE` -> `AVE`, `BOULEVARD` -> `BLVD`, etc.)
- Single quotes doubled for Socrata SoQL escaping
