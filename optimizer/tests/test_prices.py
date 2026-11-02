import csv
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from geocoding.prices import (
    build_station_index,
    load_price_data,
    normalize_price,
    normalize_price_record,
)


class PriceNormalizationTests(TestCase):
    def test_normalizes_station_location_and_price_fields(self):
        record = normalize_price_record(
            {
                "Truckstop Name": "  Casey's General Store #3956 ",
                "Address": "I-44, EXIT 283 & US-69",
                "City": " Big Cabin ",
                "State": "Oklahoma",
                "Country": "USA",
                "Retail Price": "$3.25",
            }
        )

        self.assertEqual(record["_normalized_name"], "caseys")
        self.assertEqual(record["_normalized_city"], "big cabin")
        self.assertEqual(record["_normalized_state"], "ok")
        self.assertEqual(record["_normalized_country"], "us")
        self.assertEqual(record["_price"], Decimal("3.25"))

    def test_invalid_prices_are_not_usable(self):
        for value in ("", "not a price", "0", "-1", "NaN", "Infinity"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_price(value))

    def test_index_uses_normalized_city_state_and_country(self):
        index = build_station_index(
            [
                {
                    "Truckstop Name": "Pilot #1243",
                    "Address": "I-8 Exit 119",
                    "City": "Gila Bend",
                    "State": "AZ",
                    "Country": "USA",
                    "Retail Price": "3.899",
                },
                {
                    "Truckstop Name": "Another station",
                    "Address": "I-70",
                    "City": "Gila Bend",
                    "State": "Arizona",
                    "Country": "United States",
                    "Retail Price": "3.50",
                },
            ]
        )

        self.assertEqual(len(index[("gila bend", "az", "us")]), 2)

    def test_loader_validates_headers_and_reads_csv(self):
        rows = [
            {
                "Truckstop Name": "BP",
                "Address": "Main Street",
                "City": "Springfield",
                "State": "IL",
                "Country": "USA",
                "Retail Price": "3.10",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            with path.open("w", encoding="utf-8", newline="") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            index = load_price_data(path)

        self.assertEqual(
            index[("springfield", "il", "us")][0]["_price"],
            Decimal("3.10"),
        )

    def test_loader_reports_missing_required_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            path.write_text("Truckstop Name,City\nBP,Springfield\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                load_price_data(path)

    def test_exact_duplicate_csv_records_are_deduplicated(self):
        record = {
            "Truckstop Name": "BP",
            "Address": "Main Street",
            "City": "Springfield",
            "State": "IL",
            "Country": "USA",
            "Retail Price": "3.10",
        }

        index = build_station_index([record, record.copy()])

        self.assertEqual(len(index[("springfield", "il", "us")]), 1)
