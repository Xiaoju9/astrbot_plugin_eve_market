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

# PLEX is not listed in The Forge; CCP quotes it in the special GPMR-01 market.
PLEX_TYPE_ID = 44992
PLEX_REGION_ID = 19000001
PLEX_REGION_NAME = "GPMR-01"
PLEX_DEFAULT_QUANTITY = 500

_QUANTITY_RE = re.compile(r"^(?:x|×|\*)?\s*(\d{1,9})$", re.IGNORECASE)
_MESSAGE_ARTIFACT_RE = re.compile(r"\[(?:MSG_ID|CQ|At|Reply)[^\]]*\]", re.IGNORECASE)


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


def clean_message_text(value: str) -> str:
    """Remove OneBot protocol artifacts such as ``[MSG_ID:123]``.

    aiocqhttp appends these to ``message_str`` when a CQ message is
    reconstructed; they must not become part of an item name.
    """
    text = str(value or "")
    text = _MESSAGE_ARTIFACT_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(value: str) -> str:
    """Normalize an item name for matching, without destroying CJK."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    return text[:120]


def has_explicit_quantity(args: str) -> bool:
    """Return whether the final argument is an explicit quantity."""
    parts = str(args or "").strip().split()
    return bool(parts and _QUANTITY_RE.match(parts[-1]))


def parse_command_args(args: str, default_quantity: int = 1) -> tuple[str, int]:
    """Parse ``<item> [quantity]`` / ``<item> x10``.

    Returns ``(item_name, quantity)``.  Quantity is clamped to 1..1_000_000.
    """
    text = clean_message_text(args)
    if not text:
        return "", max(1, min(1_000_000, int(default_quantity or 1)))
    parts = text.split()
    quantity = int(default_quantity or 1)
    # Support the in-game shorthand ``狞獾级海军型*500`` even when it is the
    # only token.  The old implementation only looked at the last token when
    # there were at least two tokens, so ``物品*500`` silently stayed quantity 1.
    compact = re.match(r"^(?P<item>.+?)(?:[*×]\s*|\s+[xX]\s*)(?P<qty>\d{1,9})$", text, re.IGNORECASE)
    if compact:
        item = compact.group("item").strip()
        if item:
            quantity = int(compact.group("qty"))
            quantity = max(1, min(1_000_000, quantity))
            return item, quantity
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
    source_note: str = "宁静官方 ESI",
) -> str:
    """Render the same layout the Koishi evemarket2 plugin uses.

    The source plugin replies with plain text:
        item
         -出售：1,234 ISK(volume)
         -收购：1,200 ISK(volume)
         -中间：1,217 ISK
    AstrBot cannot send the ``<p>`` wrapper, so the layout is kept and the
    location/source footer is added as plain text.
    """
    name = item.display_name if isinstance(item, MarketItem) else str(item)
    if isinstance(item, MarketItem) and item.type_id == PLEX_TYPE_ID:
        name = "PLEX"
    quantity = max(1, int(quantity or 1))
    fetched_at = fetched_at or datetime.now(timezone.utc)
    _ = fetched_at  # kept for API compatibility; the source format has no clock

    if summary.sell_min is None and summary.buy_max is None:
        return "\n".join(
            [
                name,
                "没有找到有效的买卖单。",
                "-----------------------",
                f"地点：{station_label}",
                f"数据来源：{source_note}",
            ]
        )

    sell = summary.sell_min
    buy = summary.buy_max
    mid = (sell + buy) / 2 if sell is not None and buy is not None else None
    sell_text = fmt_isk(sell)
    buy_text = fmt_isk(buy)
    mid_text = fmt_isk(mid)

    lines = [
        name,
        f" -出售：{sell_text}（{fmt_int(summary.sell_min_volume)}）",
        f" -收购：{buy_text}（{fmt_int(summary.buy_max_volume)}）",
        f" -中间：{mid_text}",
    ]
    if quantity > 1:
        lines += [
            f"{name}*{quantity}",
            f" -出售：{fmt_isk(sell * quantity if sell is not None else None)}",
            f" -收购：{fmt_isk(buy * quantity if buy is not None else None)}",
            f" -中间：{fmt_isk(mid * quantity if mid is not None else None)}",
        ]
    lines += [
        "-----------------------",
        f"地点：{station_label}",
        f"数据来源：{source_note}",
    ]
    return "\n".join(lines)


def suggestion_list(names: Iterable[str], limit: int = 6) -> str:
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    if not cleaned:
        return ""
    return "、".join(cleaned[:limit])
