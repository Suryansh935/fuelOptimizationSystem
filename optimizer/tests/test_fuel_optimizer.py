from unittest import TestCase

from optimizer.fuel_optimizer import optimize_fuel_stops


def station(
    place_id,
    distance,
    price,
    name=None,
    status="VERIFIED",
):
    return {
        "type": "Feature",
        "properties": {
            "place_id": place_id,
            "name": name or f"Station {place_id}",
            "distance_along_route_miles": distance,
            "csv_price_per_gallon": price,
            "match_status": status,
            "lat": 41.5,
            "lon": -87.5,
        },
        "geometry": {"type": "Point", "coordinates": [-87.5, 41.5]},
    }


class FuelOptimizerTests(TestCase):
    def test_destination_is_reachable_without_refuelling(self):
        result = optimize_fuel_stops([], 100)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_fuel_cost"], 0)
        self.assertEqual(result["remaining_fuel_gallons"], 40)
        self.assertEqual(result["selected_stations"], [])

    def test_vehicle_refuels_before_a_reachable_station_gap(self):
        result = optimize_fuel_stops(
            [station("A", 400, "3.40")],
            800,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["selected_stations"]), 1)
        self.assertEqual(result["selected_stations"][0]["fuel_purchased"], 40)
        self.assertEqual(result["total_fuel_cost"], 136)

    def test_full_refill_decision_accounts_for_cheaper_station_ahead(self):
        result = optimize_fuel_stops(
            [
                station("A", 200, "5.00"),
                station("B", 550, "2.00"),
            ],
            800,
        )

        stops = result["selected_stations"]
        self.assertEqual([stop["id"] for stop in stops], ["A", "B"])
        self.assertEqual([stop["fuel_purchased"] for stop in stops], [20, 35])
        self.assertEqual(result["total_fuel_cost"], 170)

    def test_skips_an_expensive_station(self):
        result = optimize_fuel_stops(
            [
                station("expensive", 300, "5.00"),
                station("cheap", 450, "2.00"),
            ],
            700,
        )

        stops = result["selected_stations"]
        self.assertEqual([stop["id"] for stop in stops], ["cheap"])
        self.assertEqual(stops[0]["fuel_purchased"], 45)
        self.assertEqual(result["total_fuel_cost"], 90)

    def test_refill_always_fills_tank_to_capacity(self):
        result = optimize_fuel_stops(
            [station("partial", 300, "3.00")],
            550,
        )

        stop = result["selected_stations"][0]
        self.assertEqual(stop["fuel_before_refueling"], 20)
        self.assertEqual(stop["fuel_purchased"], 30)
        self.assertEqual(stop["fuel_after_refueling"], 50)
        self.assertEqual(result["total_fuel_cost"], 90)

    def test_station_with_null_price_is_passed_without_refuelling(self):
        result = optimize_fuel_stops(
            [
                station("unpriced", 300, None, status="NOT_FOUND"),
                station("priced", 400, "3.00"),
            ],
            800,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            [stop["id"] for stop in result["selected_stations"]],
            ["priced"],
        )
        self.assertEqual(result["selected_stations"][0]["fuel_purchased"], 40)
        self.assertEqual(result["total_fuel_cost"], 120)

    def test_tank_capacity_is_never_exceeded(self):
        result = optimize_fuel_stops(
            [
                station("first", 400, "3.00"),
                station("second", 700, "3.00"),
            ],
            900,
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(
            all(
                stop["fuel_after_refueling"] <= 50
                for stop in result["selected_stations"]
            )
        )
        self.assertLessEqual(result["remaining_fuel_gallons"], 50)

    def test_destination_can_be_reached_with_fuel_remaining(self):
        result = optimize_fuel_stops([], 200)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["remaining_fuel_gallons"], 30)

    def test_no_feasible_route_without_usable_refuelling_stations(self):
        result = optimize_fuel_stops(
            [station("unpriced", 250, None, status="NEEDS_REVIEW")],
            600,
        )

        self.assertEqual(result["status"], "failure")
        self.assertIsNone(result["total_fuel_cost"])
        self.assertIsNone(result["remaining_fuel_gallons"])
        self.assertEqual(result["selected_stations"], [])

    def test_refills_at_earlier_station_when_full_tank_is_needed(self):
        result = optimize_fuel_stops(
            [station("reachable", 400, "3.00")],
            800,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            [stop["id"] for stop in result["selected_stations"]],
            ["reachable"],
        )
        self.assertEqual(result["selected_stations"][0]["fuel_purchased"], 40)

    def test_cannot_refill_if_full_tank_cannot_reach_the_next_point(self):
        result = optimize_fuel_stops(
            [station("too-far", 600, "3.00")],
            800,
        )

        self.assertEqual(result["status"], "failure")
        self.assertIn("cannot be reached", result["message"])

    def test_unverified_numeric_price_is_not_used(self):
        result = optimize_fuel_stops(
            [station("review", 250, "0.01", status="NEEDS_REVIEW")],
            600,
        )

        self.assertEqual(result["status"], "failure")
        self.assertIsNone(result["total_fuel_cost"])

    def test_explicit_dataset_average_is_used_as_an_estimate(self):
        candidate = station("estimated", 400, None, status="NOT_FOUND")
        candidate["properties"]["optimizer_price_per_gallon"] = "3.50"
        candidate["properties"]["optimizer_price_source"] = "dataset_average"

        result = optimize_fuel_stops([candidate], 800)

        self.assertEqual(result["status"], "success")
        stop = result["selected_stations"][0]
        self.assertEqual(stop["price_per_gallon"], 3.5)
        self.assertEqual(stop["price_source"], "dataset_average")
        self.assertTrue(stop["is_estimated_price"])
        self.assertEqual(stop["purchase_cost"], 140)

    def test_reconstructed_stops_match_the_minimum_dp_cost(self):
        result = optimize_fuel_stops(
            [
                station("cheap", 300, "3.00"),
                station("expensive", 400, "4.00"),
            ],
            700,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            sum(stop["purchase_cost"] for stop in result["selected_stations"]),
            result["total_fuel_cost"],
        )
        self.assertEqual(
            [stop["id"] for stop in result["selected_stations"]],
            ["cheap"],
        )

    def test_exact_fuel_consumption_matches_distance_divided_by_economy(self):
        result = optimize_fuel_stops(
            [],
            123.4,
            tank_capacity=50,
            fuel_economy=10,
            initial_fuel=50,
        )

        self.assertEqual(result["status"], "success")
        self.assertAlmostEqual(
            result["total_fuel_consumed_gallons"],
            123.4 / 10,
        )
        self.assertGreaterEqual(
            result["conservative_fuel_consumed_gallons"],
            result["total_fuel_consumed_gallons"],
        )

    def test_excludes_stations_outside_the_route_distance(self):
        result = optimize_fuel_stops(
            [
                station("before", -1, "1.00"),
                station("after", 601, "1.00"),
            ],
            600,
        )

        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["selected_stations"], [])

    def test_uses_feature_geometry_when_station_lat_lon_are_missing(self):
        candidate = station("geometry", 400, "3.00")
        del candidate["properties"]["lat"]
        del candidate["properties"]["lon"]

        result = optimize_fuel_stops([candidate], 800)

        self.assertEqual(result["status"], "success")
        stop = result["selected_stations"][0]
        self.assertEqual(stop["latitude"], 41.5)
        self.assertEqual(stop["longitude"], -87.5)

    def test_vehicle_configuration_is_customizable(self):
        result = optimize_fuel_stops(
            [],
            120,
            tank_capacity=30,
            fuel_economy=15,
            initial_fuel=10,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["initial_fuel_gallons"], 10)
        self.assertEqual(result["remaining_fuel_gallons"], 2)
