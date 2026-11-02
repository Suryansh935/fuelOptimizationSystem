import csv
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from geocoding.filter_stations import filter_stations_near_route
from geocoding import geocode
from geocoding.prices import build_station_index
from geocoding.route_stations import (
    build_route_station_result,
    get_route_stations_with_prices,
)


ROUTE = {
    "distance_miles": 100,
    "duration_minutes": 120,
    "geometry": {
        "type": "LineString",
        "coordinates": [
            [-90.0, 38.0],
            [-89.5, 38.0],
            [-89.0, 38.0],
        ],
    },
}


def station(place_id, longitude, name="Ayerco 24"):
    return {
        "type": "Feature",
        "properties": {
            "place_id": place_id,
            "name": name,
            "city": "Example City",
            "state_code": "MO",
            "country_code": "us",
            "lat": 38.0,
            "lon": longitude,
            "street": "Route 1",
        },
        "geometry": {
            "type": "Point",
            "coordinates": [longitude, 38.0],
        },
    }


def price_index():
    return build_station_index(
        [
            {
                "Truckstop Name": "AYERCO #24",
                "Address": "US-36 & SR-15",
                "City": "Example City",
                "State": "MO",
                "Country": "USA",
                "Retail Price": "3.25",
            }
        ]
    )


class RouteStationServiceTests(TestCase):
    def test_corridor_filter_uses_route_coordinates_and_sets_position(self):
        on_route = station("on-route", -89.5)
        near_route = station("near-route", -89.5)
        near_route["properties"]["lat"] = 38.01
        outside = station("outside", -89.5)
        outside["properties"]["lat"] = 38.04

        filtered = filter_stations_near_route(
            [on_route, near_route, outside],
            ROUTE["geometry"],
            max_distance_km=2,
        )

        self.assertEqual(
            [item["properties"]["place_id"] for item in filtered],
            ["on-route", "near-route"],
        )
        self.assertAlmostEqual(
            filtered[0]["properties"]["route_position_fraction"],
            0.5,
            places=2,
        )

    def test_build_result_returns_map_features_with_verified_prices(self):
        result = build_route_station_result(
            ROUTE,
            [station("station-1", -89.5)],
            price_index(),
        )

        self.assertEqual(result["route"]["geometry"], ROUTE["geometry"])
        features = result["stations"]["features"]
        self.assertEqual(len(features), 1)
        properties = features[0]["properties"]
        self.assertEqual(properties["match_status"], "VERIFIED")
        self.assertEqual(properties["csv_price_per_gallon"], "3.25")
        self.assertEqual(properties["distance_along_route_miles"], 50.0)

    def test_route_stations_are_ordered_and_deduplicated(self):
        result = build_route_station_result(
            ROUTE,
            [
                station("later", -89.1),
                station("earlier", -89.9),
                station("earlier", -89.9),
            ],
            price_index(),
        )

        features = result["stations"]["features"]
        self.assertEqual([f["properties"]["place_id"] for f in features],
                         ["earlier", "later"])
        self.assertLess(
            features[0]["properties"]["distance_along_route_miles"],
            features[1]["properties"]["distance_along_route_miles"],
        )

    def test_same_station_duplicate_with_different_provider_ids_is_removed(self):
        first = station("provider-id-1", -89.5)
        duplicate = station("provider-id-2", -89.5002)
        first["properties"]["formatted"] = "Ayerco, Route 1, Example City, MO"
        duplicate["properties"]["formatted"] = first["properties"]["formatted"]

        result = build_route_station_result(
            ROUTE,
            [first, duplicate],
            price_index(),
        )

        self.assertEqual(len(result["stations"]["features"]), 1)
        self.assertEqual(result["duplicates_removed"], 1)

    def test_unmatched_stations_do_not_receive_prices(self):
        result = build_route_station_result(
            ROUTE,
            [station("station-1", -89.5, name="Unrelated Fuel")],
            price_index(),
        )

        properties = result["stations"]["features"][0]["properties"]
        self.assertEqual(properties["match_status"], "NOT_FOUND")
        self.assertIsNone(properties["csv_price_per_gallon"])

    def test_entry_point_uses_one_route_and_one_station_request(self):
        row = {
            "Truckstop Name": "AYERCO #24",
            "Address": "US-36 & SR-15",
            "City": "Example City",
            "State": "MO",
            "Country": "USA",
            "Retail Price": "3.25",
        }
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "prices.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=row.keys())
                writer.writeheader()
                writer.writerow(row)

            simplified_geometry = {
                "type": "LineString",
                "coordinates": [
                    ROUTE["geometry"]["coordinates"][0],
                    ROUTE["geometry"]["coordinates"][-1],
                ],
            }
            with (
                patch("geocoding.route_stations.get_route", return_value=ROUTE) as route,
                patch(
                    "geocoding.route_stations.simplify_route_geometry",
                    return_value=simplified_geometry,
                ) as simplify,
                patch(
                    "geocoding.route_stations.filter_stations_near_route",
                    wraps=filter_stations_near_route,
                ) as filter_route,
                patch(
                    "geocoding.route_stations.search_fuel_stations_along_route",
                    return_value=[station("station-1", -89.5)],
                ) as search,
            ):
                result = get_route_stations_with_prices(
                    (-90.0, 38.0),
                    (-89.0, 38.0),
                    price_csv_path=csv_path,
                )

        route.assert_called_once_with((-90.0, 38.0), (-89.0, 38.0))
        simplify.assert_called_once_with(ROUTE["geometry"])
        search.assert_called_once()
        self.assertEqual(filter_route.call_args.args[1], ROUTE["geometry"])
        self.assertEqual(result["route"]["geometry"], simplified_geometry)
        self.assertEqual(
            result["external_request_count"],
            {"osrm": 1, "geoapify": 1},
        )
        self.assertEqual(
            result["stations"]["features"][0]["properties"]["csv_price_per_gallon"],
            "3.25",
        )

    def test_geoapify_search_paginates_and_reports_request_count(self):
        first_page = type(
            "Response",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {
                    "features": [{"id": "one"}, {"id": "two"}]
                },
            },
        )()
        second_page = type(
            "Response",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {"features": [{"id": "three"}]},
            },
        )()

        with (
            patch("geocoding.geocode.API_KEY", "test-key"),
            patch(
                "geocoding.geocode.requests.post",
                side_effect=[first_page, second_page],
            ) as post,
        ):
            result = geocode.search_fuel_stations_along_route(
                ROUTE["geometry"],
                limit=2,
                max_pages=3,
                return_metadata=True,
            )

        self.assertEqual([feature["id"] for feature in result["features"]],
                         ["one", "two", "three"])
        self.assertEqual(result["requests_made"], 2)
        self.assertFalse(result["truncated"])
        self.assertEqual(
            [call.kwargs["params"]["offset"] for call in post.call_args_list],
            [0, 2],
        )

    def test_geoapify_search_marks_pagination_limit_as_truncated(self):
        full_page = type(
            "Response",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {
                    "features": [{"id": "one"}, {"id": "two"}]
                },
            },
        )()
        with (
            patch("geocoding.geocode.API_KEY", "test-key"),
            patch(
                "geocoding.geocode.requests.post",
                return_value=full_page,
            ),
        ):
            result = geocode.search_fuel_stations_along_route(
                ROUTE["geometry"],
                limit=2,
                max_pages=1,
                return_metadata=True,
            )

        self.assertTrue(result["truncated"])
