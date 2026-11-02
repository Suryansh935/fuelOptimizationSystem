import json
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from django.test import Client
from django.urls import reverse

from optimizer.services import LocationNotFoundError, geocode_us_location


class RouteStationsApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        geocode_us_location.cache_clear()

    def tearDown(self):
        geocode_us_location.cache_clear()

    @patch(
        "optimizer.services.get_average_dataset_fuel_price",
        return_value=Decimal("3.50"),
    )
    @patch("optimizer.services.get_route_stations_with_prices")
    @patch("optimizer.services.search_geocoding")
    def test_post_geocodes_us_locations_and_returns_route_response(
        self,
        search_geocoding,
        get_route_stations,
        get_average_price,
    ):
        search_geocoding.side_effect = [
            [
                {
                    "country_code": "us",
                    "lat": 41.8781,
                    "lon": -87.6298,
                    "formatted": "Chicago, IL, USA",
                }
            ],
            [
                {
                    "country_code": "us",
                    "lat": 39.0997,
                    "lon": -94.5786,
                    "formatted": "Kansas City, MO, USA",
                }
            ],
        ]
        get_route_stations.return_value = {
            "route": {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-87.6298, 41.8781], [-94.5786, 39.0997]],
                },
                "properties": {"distance_miles": 1100, "duration_minutes": 1200},
            },
            "stations": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "place_id": "unpriced-station-1",
                            "name": "Unpriced Station 1",
                            "distance_along_route_miles": 800,
                            "match_status": "NOT_FOUND",
                            "csv_price_per_gallon": None,
                            "lat": 39.0,
                            "lon": -90.0,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-90.0, 39.0],
                        },
                    },
                    {
                        "type": "Feature",
                        "properties": {
                            "place_id": "unpriced-station-2",
                            "name": "Unpriced Station 2",
                            "distance_along_route_miles": 400,
                            "match_status": "NOT_FOUND",
                            "csv_price_per_gallon": None,
                            "lat": 38.0,
                            "lon": -91.0,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [-91.0, 38.0],
                        },
                    },
                ],
            },
            "external_request_count": {"osrm": 1, "geoapify": 1},
        }

        response = self.client.post(
            reverse("route-plan"),
            data=json.dumps(
                {"start": "Chicago, IL", "destination": "Kansas City, MO"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["locations"]["start"]["coordinates"], [-87.6298, 41.8781])
        self.assertEqual(
            body["locations"]["destination"]["coordinates"],
            [-94.5786, 39.0997],
        )
        self.assertEqual(body["geocoding_lookups"], 2)
        self.assertEqual(
            body["stations"],
            ["Unpriced Station 2", "Unpriced Station 1"],
        )
        self.assertEqual(
            body["fuel_optimization"]["status"],
            "success",
        )
        self.assertEqual(
            body["fuel_optimization"]["selected_station_names"],
            ["Unpriced Station 2", "Unpriced Station 1"],
        )
        self.assertEqual(
            body["fuel_optimization"]["selected_stations"],
            [
                {
                    "id": "unpriced-station-2",
                    "name": "Unpriced Station 2",
                },
                {
                    "id": "unpriced-station-1",
                    "name": "Unpriced Station 1",
                },
            ],
        )
        self.assertEqual(
            body["fuel_optimization"]["fuel_economy_mpg"],
            10,
        )
        self.assertEqual(
            body["fuel_optimization"]["total_fuel_cost"],
            280,
        )
        self.assertEqual(
            body["fuel_optimization"]["price_assumptions"][
                "dataset_average_price_per_gallon"
            ],
            3.5,
        )
        get_average_price.assert_called_once_with()
        search_geocoding.assert_any_call("Chicago, IL, USA", limit=5)
        search_geocoding.assert_any_call("Kansas City, MO, USA", limit=5)
        get_route_stations.assert_called_once_with(
            start=(-87.6298, 41.8781),
            end=(-94.5786, 39.0997),
        )

    def test_rejects_invalid_json_and_missing_locations(self):
        invalid_json = self.client.post(
            reverse("route-plan"),
            data="{",
            content_type="application/json",
        )
        missing_location = self.client.post(
            reverse("route-plan"),
            data=json.dumps({"start": "Chicago, IL"}),
            content_type="application/json",
        )

        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(missing_location.status_code, 400)

    @patch("optimizer.views.build_route_station_response")
    def test_post_does_not_require_csrf_token_for_api_clients(self, build_response):
        build_response.return_value = {"route": {}, "stations": {}}
        csrf_checked_client = Client(enforce_csrf_checks=True)

        response = csrf_checked_client.post(
            reverse("route-plan"),
            data=json.dumps(
                {"start": "Chicago, IL", "destination": "Kansas City, MO"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        build_response.assert_called_once_with("Chicago, IL", "Kansas City, MO")

    @patch("optimizer.services.search_geocoding")
    def test_does_not_accept_non_us_geocoding_result(self, search_geocoding):
        search_geocoding.return_value = [
            {
                "country_code": "ca",
                "lat": 43.6532,
                "lon": -79.3832,
                "formatted": "Toronto, Canada",
            }
        ]

        with self.assertRaises(LocationNotFoundError):
            geocode_us_location("Toronto, Canada")

    @patch("optimizer.services.search_geocoding")
    def test_geocoding_cache_reuses_repeated_location(self, search_geocoding):
        search_geocoding.return_value = [
            {
                "country_code": "us",
                "lat": 41.8781,
                "lon": -87.6298,
                "formatted": "Chicago, IL, USA",
            }
        ]

        first = geocode_us_location("Chicago, IL")
        second = geocode_us_location("Chicago, IL")

        self.assertEqual(first, second)
        search_geocoding.assert_called_once()

    @patch("optimizer.views.build_route_station_response")
    def test_returns_unprocessable_for_unresolved_location(self, build_response):
        build_response.side_effect = LocationNotFoundError(
            "Could not resolve location in the United States"
        )

        response = self.client.post(
            reverse("route-plan"),
            data=json.dumps({"start": "Unknown", "destination": "Chicago, IL"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("United States", response.json()["error"])
