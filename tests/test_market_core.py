from __future__ import annotations

import unittest
from datetime import datetime, timezone

from market_core import (
    JITA_STATION_ID,
    MarketItem,
    PriceSummary,
    clean_message_text,
    format_price,
    normalize_name,
    parse_command_args,
    summarize_orders,
)


def order(price: float, volume: int, buy: bool, location: int = JITA_STATION_ID) -> dict:
    return {
        "price": price,
        "volume_remain": volume,
        "is_buy_order": buy,
        "location_id": location,
    }


class ParseTests(unittest.TestCase):
    def test_plain_item(self) -> None:
        self.assertEqual(parse_command_args("乌鸦级"), ("乌鸦级", 1))

    def test_quantity_suffix(self) -> None:
        self.assertEqual(parse_command_args("乌鸦级 10"), ("乌鸦级", 10))
        self.assertEqual(parse_command_args("狞獾级海军型 x5"), ("狞獾级海军型", 5))

    def test_quantity_compact_suffix(self) -> None:
        self.assertEqual(parse_command_args("狞獾级海军型*500"), ("狞獾级海军型", 500))
        self.assertEqual(parse_command_args("Raven*500"), ("Raven", 500))
        self.assertEqual(parse_command_args("PLEX ×500"), ("PLEX", 500))

    def test_message_id_suffix_is_stripped(self) -> None:
        self.assertEqual(
            parse_command_args("狞獾级海军型 [MSG_ID:-1850447759]"),
            ("狞獾级海军型", 1),
        )
        self.assertEqual(parse_command_args("plex [MSG_ID:1479643879]"), ("plex", 1))

    def test_clean_message_text(self) -> None:
        self.assertEqual(clean_message_text("乌鸦级 [MSG_ID:123]"), "乌鸦级")
        self.assertEqual(clean_message_text("[MSG_ID:123] 乌鸦级"), "乌鸦级")

    def test_item_with_space(self) -> None:
        self.assertEqual(parse_command_args("Large Shield Transporter II"), ("Large Shield Transporter II", 1))

    def test_quantity_clamped(self) -> None:
        _, quantity = parse_command_args("乌鸦级 99999999")
        self.assertEqual(quantity, 1_000_000)


class SummaryTests(unittest.TestCase):
    def test_best_prices_and_volume(self) -> None:
        summary = summarize_orders(
            [
                order(100, 10, False),
                order(99, 5, False),
                order(98, 3, False),
                order(90, 7, True),
                order(91, 2, True),
                order(89, 20, True),
            ]
        )
        self.assertEqual(summary.sell_min, 98)
        self.assertEqual(summary.sell_min_volume, 3)
        self.assertEqual(summary.sell_total_volume, 18)
        self.assertEqual(summary.buy_max, 91)
        self.assertEqual(summary.buy_max_volume, 2)
        self.assertEqual(summary.buy_total_volume, 29)
        self.assertEqual(summary.spread, 7)
        self.assertAlmostEqual(summary.spread_pct or 0, 7 / 98 * 100)

    def test_station_filter(self) -> None:
        summary = summarize_orders(
            [
                order(100, 10, False, location=60003760),
                order(50, 10, False, location=60008494),
            ],
            station_id=60003760,
        )
        self.assertEqual(summary.sell_min, 100)
        self.assertTrue(summary.used_station)

    def test_empty_side(self) -> None:
        summary = summarize_orders([order(100, 10, False)])
        self.assertIsNone(summary.buy_max)
        self.assertIsNone(summary.spread)

    def test_ignores_bad_orders(self) -> None:
        summary = summarize_orders(
            [
                {"price": None, "volume": 1, "is_buy_order": False},
                {"price": 10, "volume": 0, "is_buy_order": False},
                {"price": -1, "volume": 5, "is_buy_order": False},
            ]
        )
        self.assertIsNone(summary.sell_min)

    def test_esi_volume_remain_is_counted(self) -> None:
        summary = summarize_orders(
            [
                {
                    "price": 100.0,
                    "volume_remain": 7,
                    "is_buy_order": False,
                    "location_id": JITA_STATION_ID,
                }
            ]
        )
        self.assertEqual(summary.sell_min, 100.0)
        self.assertEqual(summary.sell_total_volume, 7)
        self.assertEqual(summary.sell_min_volume, 7)

    def test_real_esi_volume_remain_and_legacy_volume(self) -> None:
        summary = summarize_orders(
            [
                {"price": 5.0, "volume_remain": 10, "is_buy_order": True, "location_id": JITA_STATION_ID},
                {"price": 6.0, "volume": 20, "is_buy_order": True, "location_id": JITA_STATION_ID},
            ]
        )
        self.assertEqual(summary.buy_max, 6.0)
        self.assertEqual(summary.buy_total_volume, 30)

    def test_format_contains_key_fields(self) -> None:
        text = format_price(
            MarketItem(type_id=638, name_zh="乌鸦级"),
            PriceSummary(
                sell_min=123_000_000,
                sell_min_volume=12,
                sell_total_volume=100,
                sell_orders=4,
                buy_max=120_000_000,
                buy_max_volume=30,
                buy_total_volume=200,
                buy_orders=3,
                spread=3_000_000,
                spread_pct=2.44,
                used_station=True,
            ),
            quantity=10,
            fetched_at=datetime(2026, 10, 26, tzinfo=timezone.utc),
        )
        self.assertIn("乌鸦级", text)
        self.assertIn("乌鸦级*10", text)
        self.assertIn(" -出售：123,000,000 ISK（12）", text)
        self.assertIn(" -收购：120,000,000 ISK（30）", text)
        self.assertIn(" -中间：121,500,000 ISK", text)
        self.assertIn("数据来源：宁静官方 ESI", text)


class NormalizeTests(unittest.TestCase):
    def test_width_and_space(self) -> None:
        self.assertEqual(normalize_name("  Ｒａｖｅｎ  "), "raven")
        self.assertEqual(normalize_name("乌鸦 级"), "乌鸦级")


if __name__ == "__main__":
    unittest.main()
