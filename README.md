# Pakistan-ThermoRail-Engine

A map of heat exposure along Pakistan's railway network, built from open data.

## What it does
Takes the railway lines from OpenStreetMap, cuts them into pieces of about 1 km,
and gives each piece a heat tier based on air and ground temperature over
May and June 2026.

## How it was built
1. Downloaded railway ways for Pakistan from OpenStreetMap (Overpass API).
2. Kept ways tagged as main or branch line, and added untagged ways that connect to the
   main network. Dropped sidings, yards and spurs. Each kept way has a `confidence`
   label (high, medium, low).
3. Split the 4,158 kept ways into 10,216 pieces of at most 1.5 km.
4. Pulled hourly air temperature and 0-7 cm soil temperature for 787 grid cells
   (May 1 to June 30, 2026) from Open-Meteo's historical archive.
5. Scored each cell by averaging its air and soil rank (95th percentile of each),
   then cut the scores into four tiers: moderate, elevated, high, extreme.

## Files
- `pk_rail_heat_v2.geojson`: the final pieces with tiers
- `cell_heat.csv`: temperature summary per grid cell

## Limits
- Temperatures come from a weather model with cells of about 10 km. Many pieces share one value.
- Soil temperature is a proxy. It is not a measurement of rail temperature.
- It covers one season of one year.
- Tiers are relative. "Extreme" means the top 5% of cells in this network, not a
  physical threshold for track damage.
- OpenStreetMap coverage is uneven, and some real track may be missing or mislabeled.

## Credits
Railway geometry: (c) OpenStreetMap contributors (ODbL).
Weather data: Open-Meteo.com (CC BY 4.0), based on ERA5 and ERA5-Land from Copernicus.
