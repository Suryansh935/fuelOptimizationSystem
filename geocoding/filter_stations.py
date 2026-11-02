
from shapely.geometry import LineString, Point
from shapely.ops import transform
from pyproj import CRS, Transformer


def filter_stations_near_route(
    stations,
    route_geometry,
    max_distance_km=2
):
    coordinates = route_geometry["coordinates"]
    if len(coordinates) < 2:
        raise ValueError("Route geometry must contain at least two coordinates")

    center_lon = sum(coordinate[0] for coordinate in coordinates) / len(coordinates)
    center_lat = sum(coordinate[1] for coordinate in coordinates) / len(coordinates)
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} "
        "+datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs(
        "EPSG:4326",
        local_crs,
        always_xy=True
    )

    route_line = LineString(coordinates)
    projected_route = transform(
        transformer.transform,
        route_line
    )

    filtered_stations = []

    for station in stations:
        properties = station.get("properties", {})

        lat = properties.get("lat")
        lon = properties.get("lon")

        if lat is None or lon is None:
            continue

        station_point = Point(lon, lat)

        projected_station = transform(
            transformer.transform,
            station_point
        )

        distance_m = projected_route.distance(projected_station)

        if distance_m <= max_distance_km * 1000:
            properties["distance_from_route_km"] = round(
                distance_m / 1000, 3
            )
            properties["route_position_fraction"] = (
                projected_route.project(projected_station)
                / projected_route.length
            )
            filtered_stations.append(station)

    return filtered_stations
