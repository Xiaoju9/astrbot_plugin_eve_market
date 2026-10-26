"""Pure helpers for the EVE market plugin.

Kept free of AstrBot imports so the pricing logic can be unit-tested on a
plain Python interpreter.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

JITA_REGION_ID = 10000002  # The Forge
JITA_STATION_ID = 60003760  # Jita IV - Moon 4 - Caldari Navy Assembly Plant
JITA_STATION_NAME = "吉他 4-4"

_QUANTITY_RE = re.compile(r"^(?:x|×|\*)?\s*(\d{1,9})$", re.IGNORECASE)


@dataclass
class MarketItem:
    type_id: int
    name_zh: str = ""
    name_en: str = ""
    group_id: int | None = None
    volume: float | None = None

    @property
    def display_name(self) -> str:
        return self.name_zh or self.name_en or f"type {self.type_id}"


@dataclass
class PriceSummary:
    sell_min: float | None = None
    sell_min_volume: int = 0
    sell_total_volume: int = 0
    sell_orders: int = 0
    buy_max: float | None = None
    buy_max_volume: int = 0
    buy_total_volume: int = 0
    buy_orders: int = 0
    spread: float | None = None
    spread_pct: float | None = None
    used_station: bool = False
    pages: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "sell_min": self.sell_min,
            "sell_min_volume": self.sell_min_volume,
            "sell_total_volume": self.sell_total_volume,
            "sell_orders": self.sell_orders,
            "buy_max": self.buy_max,
            "buy_max_volume": self.buy_max_volume,
            "buy_total_volume": self.buy_total_volume,
            "buy_orders": self.buy_orders,
            "spread": self.spread,
            "spread_pct": self.spread_pct,
            "used_station": self.used_station,
            "pages": self.pages,
        }


def normalize_name(value: str) -> str:
    """Normalize an item/alias name for matching, without destroying CJK."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text[:120]


def parse_command_args(args: str, default_quantity: int = 1) -> tuple[str, int]:
    """Parse ``<item> [quantity]`` / ``<item> x10``.

    Returns ``(item_name, quantity)``.  Quantity is clamped to 1..1_000_000.
    """
    text = str(args or "").strip()
    if not text:
        return "", max(1, min(1_000_000, int(default_quantity or 1)))
    parts = text.split()
    quantity = int(default_quantity or 1)
    if len(parts) >= 2:
        match = _QUANTITY_RE.match(parts[-1])
        if match:
            quantity = int(match.group(1))
            parts = parts[:-1]
    item = " ".join(parts).strip()
    quantity = max(1, min(1_000_000, quantity))
    return item, quantity


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def summarize_orders(
    orders: Iterable[dict[str, Any]],
    *,
    station_id: int | None = JITA_STATION_ID,
    pages: int = 1,
) -> PriceSummary:
    """Aggregate ESI market orders into best bid/ask and volumes.

    ``station_id`` filters to one station when provided.  If that station has
    no orders, the caller can retry with ``station_id=None`` for region-wide
    prices.
    """
    sells: list[tuple[float, int]] = []
    buys: list[tuple[float, int]] = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        if station_id is not None:
            try:
                if int(order.get("location_id") or 0) != int(station_id):
                    continue
            except (TypeError, ValueError):
                continue
        price = _num(order.get("price"))
        volume = _num(order.get("volume_remain"))
        if volume is None:
            volume = _num(order.get("volume"))
        if price is None or volume is None or volume <= 0:
            continue
        if bool(order.get("is_buy_order")):
            buys.append((price, int(volume)))
        else:
            sells.append((price, int(volume)))

    summary = PriceSummary(pages=max(1, int(pages or 1)))
    if sells:
        sells.sort(key=lambda row: row[0])
        best = sells[0][0]
        summary.sell_min = best
        summary.sell_orders = len(sells)
        summary.sell_min_volume = sum(vol for price, vol in sells if price <= best * 1.0000001)
        summary.sell_total_volume = sum(vol for _, vol in sells)
    if buys:
        buys.sort(key=lambda row: row[0], reverse=True)
        best = buys[0][0]
        summary.buy_max = best
        summary.buy_orders = len(buys)
        summary.buy_max_volume = sum(vol for price, vol in buys if price >= best * 0.9999999)
        summary.buy_total_volume = sum(vol for _, vol in buys)
    if summary.sell_min is not None and summary.buy_max is not None:
        summary.spread = summary.sell_min - summary.buy_max
        if summary.sell_min > 0:
            summary.spread_pct = summary.spread / summary.sell_min * 100.0
    summary.used_station = station_id is not None
    return summary


def fmt_isk(value: float | None) -> str:
    if value is None:
        return "无"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f}B ISK"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.2f}M ISK"
    return f"{value:,.0f} ISK"


def fmt_int(value: int | None) -> str:
    if value is None:
        return "0"
    return f"{int(value):,}"


def format_price(
    item: MarketItem | str,
    summary: PriceSummary,
    *,
    quantity: int = 1,
    station_label: str = JITA_STATION_NAME,
    fetched_at: datetime | None = None,
    source_note: str = "ESI",
) -> str:
    name = item.display_name if isinstance(item, MarketItem) else str(item)
    quantity = max(1, int(quantity or 1))
    fetched_at = fetched_at or datetime.now(timezone.utc)
    local_time = fetched_at.astimezone().strftime("%m-%d %H:%M:%S")
    lines = [f"【{station_label}】{name}"]
    if summary.sell_min is None and summary.buy_max is None:
        lines.append("这个地点目前没有可用的买卖单。")
        lines.append(f"数据：{source_note} / {local_time}")
        return "\n".join(lines)

    if summary.sell_min is not None:
        lines.append(
            f"卖单最低：{fmt_isk(summary.sell_min)}"
            f"（该价 {fmt_int(summary.sell_min_volume)} 件，卖单共 {fmt_int(summary.sell_total_volume)} 件）"
        )
    else:
        lines.append("卖单最低：无")
    if summary.buy_max is not None:
        lines.append(
            f"收单最高：{fmt_isk(summary.buy_max)}"
            f"（该价 {fmt_int(summary.buy_max_volume)} 件，收单共 {fmt_int(summary.buy_total_volume)} 件）"
        )
    else:
        lines.append("收单最高：无")

    if summary.spread is not None and summary.spread_pct is not None:
        lines.append(f"价差：{fmt_isk(summary.spread)}（{summary.spread_pct:.2f}%）")

    if quantity > 1:
        buy_total = summary.sell_min * quantity if summary.sell_min is not None else None
        lines.append(f"{quantity} 件按最低卖单约：{fmt_isk(buy_total)}")
    lines.append(f"数据：{source_note} / {local_time}")
    if not summary.used_station:
        lines.append("提示：该地点没有挂单，已回退到整个星域报价。")
    return "\n".join(lines)


def suggestion_list(names: Iterable[str], limit: int = 6) -> str:
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    if not cleaned:
        return ""
    return "、".join(cleaned[:limit])
