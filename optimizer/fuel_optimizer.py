

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR


FUEL_UNIT_GALLONS = Decimal("0.1")


def _decimal(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be a finite number") from None
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite number")
    return number


def _station_properties(station):
    properties = station.get("properties")
    return properties if isinstance(properties, dict) else station


def _build_points(stations, destination):
    points = [{"name": "START", "distance": Decimal("0"), "station": None}]

    for feature in stations:
        if not isinstance(feature, dict):
            continue
        properties = _station_properties(feature)
        try:
            distance = _decimal(
                properties.get("distance_along_route_miles"),
                "Station distance",
            )
        except ValueError:
            continue
        if distance < 0 or distance > destination:
            continue

        price = None
        if properties.get("match_status") == "VERIFIED":
            try:
                candidate_price = _decimal(
                    properties.get("csv_price_per_gallon"),
                    "Station price",
                )
            except ValueError:
                candidate_price = None
            if candidate_price is not None and candidate_price > 0:
                price = candidate_price
        if price is None and properties.get("optimizer_price_source") == (
            "dataset_average"
        ):
            try:
                candidate_price = _decimal(
                    properties.get("optimizer_price_per_gallon"),
                    "Estimated station price",
                )
            except ValueError:
                candidate_price = None
            if candidate_price is not None and candidate_price > 0:
                price = candidate_price

        points.append(
            {
                "distance": distance,
                "price": price,
                "station": feature,
            }
        )

    points[1:] = sorted(points[1:], key=lambda point: point["distance"])
    points.append(
        {"name": "DESTINATION", "distance": destination, "station": None}
    )
    return points


def _fuel_units(gallons, rounding):
    return int(
        (gallons / FUEL_UNIT_GALLONS).to_integral_value(rounding=rounding)
    )


def _gallons(units):
    return float(FUEL_UNIT_GALLONS * units)


def optimize_fuel_stops(
    stations,
    destination,
    tank_capacity=50,
    fuel_economy=10,
    initial_fuel=50,
):
    """Return a minimum-cost plan for station features from the route pipeline.

    At each route point, the DP considers skipping or filling the tank
    completely. Fuel consumption for each segment rounds up to the nearest
    0.1 gallon; capacity and initial fuel round down to that increment. Only
    verified stations with a positive CSV price can sell fuel.
    """
    destination = _decimal(destination, "destination")
    tank_capacity = _decimal(tank_capacity, "tank_capacity")
    fuel_economy = _decimal(fuel_economy, "fuel_economy")
    initial_fuel = _decimal(initial_fuel, "initial_fuel")
    if destination < 0:
        raise ValueError("destination must be zero or greater")
    if tank_capacity <= 0:
        raise ValueError("tank_capacity must be greater than zero")
    if fuel_economy <= 0:
        raise ValueError("fuel_economy must be greater than zero")
    if initial_fuel < 0 or initial_fuel > tank_capacity:
        raise ValueError("initial_fuel must be between zero and tank_capacity")
    if not isinstance(stations, (list, tuple)):
        raise ValueError("stations must be a list or tuple of station features")

    capacity = _fuel_units(tank_capacity, ROUND_FLOOR)
    initial = _fuel_units(initial_fuel, ROUND_FLOOR)
    if capacity < 1:
        raise ValueError("tank_capacity must be at least 0.1 gallons")

    points = _build_points(stations, destination)
    fuelStationDistance = [point["distance"] for point in points]
    fuelCost = [point.get("price") for point in points]
    stationValid = [price is not None for price in fuelCost]
    stationDetails = [point.get("station") for point in points]
    point_count = len(fuelStationDistance)

    parent = {}
    memo = {}
    
    requiredFuel = []
    conservative_consumption = 0
    for index in range(point_count - 1):
        distance = fuelStationDistance[index + 1] - fuelStationDistance[index]
        consumed = _fuel_units(
            distance / fuel_economy,
            ROUND_CEILING,
        )
        requiredFuel.append(consumed)
        conservative_consumption += consumed

    def solve(index, fuel):
        if index == point_count - 1:
            return Decimal("0") if fuel >= 0 else Decimal("Infinity")
        if (index, fuel) in memo:
            return memo[(index, fuel)]

        required = requiredFuel[index]
        infinity = Decimal("Infinity")

        skip_cost = infinity
        skip_remaining_fuel = fuel - required
        if skip_remaining_fuel >= 0:
            skip_cost = solve(index + 1, skip_remaining_fuel)

        refill_cost = infinity
        refill_purchase = 0
        refill_remaining_fuel = -1
        if stationValid[index]:
            refill_purchase = capacity - fuel
            refill_remaining_fuel = capacity - required
            if refill_remaining_fuel >= 0:
                refill_cost = (
                    FUEL_UNIT_GALLONS
                    * refill_purchase
                    * fuelCost[index]
                    + solve(index + 1, refill_remaining_fuel)
                )

        memo[(index, fuel)] = min(skip_cost, refill_cost)
        if skip_cost <= refill_cost and skip_cost.is_finite():
            parent[(index, fuel)] = (0, skip_remaining_fuel)
        elif refill_cost.is_finite():
            parent[(index, fuel)] = (
                refill_purchase,
                refill_remaining_fuel,
            )
        return memo[(index, fuel)]

    minimum_cost = solve(0, initial)
    common_result = {
        "total_route_distance_miles": float(destination),
        "initial_fuel_gallons": _gallons(initial),
        "total_fuel_consumed_gallons": float(destination / fuel_economy),
        "conservative_fuel_consumed_gallons": _gallons(
            conservative_consumption
        ),
    }
    if not minimum_cost.is_finite():
        return {
            "status": "failure",
            "message": "Destination cannot be reached with the available fuel.",
            **common_result,
            "total_fuel_cost": None,
            "remaining_fuel_gallons": None,
            "selected_stations": [],
        }

    selected_stations = []
    index = 0
    fuel = initial
    while index < point_count - 1:
        decision = parent.get((index, fuel))
        if decision is None:
            raise RuntimeError("Fuel plan is missing DP path information")
        purchased, remaining_fuel = decision
        if purchased > 0:
            feature = stationDetails[index]
            properties = _station_properties(feature)
            geometry = feature.get("geometry")
            coordinates = (
                geometry.get("coordinates", [])
                if isinstance(geometry, dict)
                else []
            )
            latitude = properties.get("lat")
            longitude = properties.get("lon")
            if latitude is None and len(coordinates) >= 2:
                longitude, latitude = coordinates[:2]
            amount = FUEL_UNIT_GALLONS * purchased
            selected_stations.append(
                {
                    "id": properties.get("place_id") or feature.get("id"),
                    "name": properties.get("name"),
                    "distance_along_route_miles": float(
                        fuelStationDistance[index]
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                    "price_per_gallon": float(fuelCost[index]),
                    "price_source": (
                        properties.get("optimizer_price_source")
                        or properties.get("price_source")
                    ),
                    "is_estimated_price": (
                        properties.get("optimizer_price_source")
                        == "dataset_average"
                    ),
                    "fuel_before_refueling": _gallons(fuel),
                    "fuel_purchased": float(amount),
                    "fuel_after_refueling": _gallons(fuel + purchased),
                    "purchase_cost": float(amount * fuelCost[index]),
                }
            )
        fuel = remaining_fuel
        index += 1

    return {
        "status": "success",
        **common_result,
        "total_fuel_cost": float(minimum_cost),
        "remaining_fuel_gallons": _gallons(fuel),
        "selected_stations": selected_stations,
    }
