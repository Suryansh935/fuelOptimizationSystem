import builtins
import importlib
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

import geocoding.match_stations as matching
from geocoding.prices import build_station_index


def csv_record(
    name="BP",
    address="Main Street",
    city="Springfield",
    state="IL",
    country="USA",
    price="3.10",
):
    return {
        "Truckstop Name": name,
        "Address": address,
        "City": city,
        "State": state,
        "Country": country,
        "Retail Price": price,
    }


def geo_station(
    name="BP",
    street="Main Street",
    city="Springfield",
    state="IL",
    country="us",
    brand=None,
):
    properties = {
        "name": name,
        "street": street,
        "city": city,
        "state_code": state,
        "country_code": country,
    }
    if brand is not None:
        properties["brand"] = brand
    return {"properties": properties}


class StationMatchingTests(TestCase):
    def test_unique_name_and_address_match_is_verified_with_price(self):
        index = build_station_index([csv_record()])

        result = matching.match_station(
            geo_station(),
            index,
        )

        self.assertEqual(result["status"], matching.VERIFIED)
        self.assertEqual(result["price"], Decimal("3.10"))
        self.assertEqual(result["candidate"]["Truckstop Name"], "BP")

    def test_name_and_location_without_address_is_review_only(self):
        index = build_station_index([csv_record()])

        result = matching.match_station(
            geo_station(street="Different Street"),
            index,
        )

        self.assertEqual(result["status"], matching.NEEDS_REVIEW)
        self.assertIsNone(result["price"])
        self.assertNotIn("Retail Price", result["candidate"])

    def test_same_brand_alone_does_not_match_missing_station_name(self):
        index = build_station_index([csv_record()])

        result = matching.match_station(
            geo_station(name=None, brand="BP"),
            index,
        )

        self.assertEqual(result["status"], matching.NOT_FOUND)
        self.assertIsNone(result["candidate"])
        self.assertIsNone(result["price"])

    def test_branch_conflict_rejects_candidate(self):
        index = build_station_index(
            [csv_record(name="BP #456")]
        )

        result = matching.match_station(
            geo_station(name="BP #123"),
            index,
        )

        self.assertEqual(result["status"], matching.NOT_FOUND)
        self.assertTrue(result["branch_conflict"])
        self.assertIsNone(result["price"])

    def test_multiple_plausible_records_are_ambiguous_without_price(self):
        index = build_station_index(
            [
                csv_record(address="First Street"),
                csv_record(address="Second Street", price="3.20"),
            ]
        )

        result = matching.match_station(
            geo_station(street="Unknown Street"),
            index,
        )

        self.assertEqual(result["status"], matching.AMBIGUOUS)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertTrue(
            all("Retail Price" not in candidate for candidate in result["candidates"])
        )
        self.assertIsNone(result["price"])

    def test_exact_station_with_invalid_price_reports_no_price(self):
        index = build_station_index([csv_record(price="not available")])

        result = matching.match_station(
            geo_station(),
            index,
        )

        self.assertEqual(result["status"], matching.NO_PRICE)
        self.assertIsNone(result["price"])
        self.assertNotIn("Retail Price", result["candidate"])

    def test_location_must_include_country_and_match_country(self):
        index = build_station_index([csv_record()])

        missing_country = matching.match_station(
            geo_station(country=None),
            index,
        )
        wrong_country = matching.match_station(
            geo_station(country="ca"),
            index,
        )

        self.assertEqual(missing_country["status"], matching.NOT_FOUND)
        self.assertEqual(wrong_country["status"], matching.NOT_FOUND)

    def test_import_has_no_file_io_side_effect(self):
        with patch.object(
            builtins,
            "open",
            side_effect=AssertionError("module import attempted file I/O"),
        ):
            importlib.reload(matching)

        self.assertTrue(callable(matching.match_station))

    def test_name_suffix_and_apostrophe_normalization_can_propose_review(self):
        index = build_station_index(
            [csv_record(name="CASEYS #3956", address="Highway 1")]
        )

        result = matching.match_station(
            geo_station(
                name="Casey's General Store",
                street="Different address",
            ),
            index,
        )

        self.assertEqual(result["status"], matching.NEEDS_REVIEW)
        self.assertIsNone(result["price"])
