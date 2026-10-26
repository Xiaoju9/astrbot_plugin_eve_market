"""EVE market price checker for AstrBot.

Only exact in-game item names (Chinese or English) are accepted.  The reply
layout follows the Koishi evemarket2 plugin.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.api.web import error_response, json_response, request

try:  # plugin package import
    from .market_core import (
        JITA_REGION_ID,
        JITA_STATION_ID,
        JITA_STATION_NAME,
        PLEX_DEFAULT_QUANTITY,
        PLEX_REGION_ID,
        PLEX_REGION_NAME,
        PLEX_TYPE_ID,
        MarketItem,
        PriceSummary,
        clean_message_text,
        fmt_int,
        fmt_isk,
        format_price,
        has_explicit_quantity,
        normalize_name,
        parse_command_args,
        summarize_orders,
    )
except ImportError:  # local unit tests
    from market_core import (  # type: ignore
        JITA_REGION_ID,
        JITA_STATION_ID,
        JITA_STATION_NAME,
        PLEX_DEFAULT_QUANTITY,
        PLEX_REGION_ID,
        PLEX_REGION_NAME,
        PLEX_TYPE_ID,
        MarketItem,
        PriceSummary,
        clean_message_text,
        fmt_int,
        fmt_isk,
        format_price,
        has_explicit_quantity,
        normalize_name,
        parse_command_args,
        summarize_orders,
    )

PLUGIN_NAME = "astrbot_plugin_eve_market"
ESI_BASE = "https://esi.evetech.net/latest"
DEFAULT_COMMANDS = "查价,市场,eve"


class EsiError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _as_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", "否"}


class EsiClient:
    """Tiny ESI client with one retry on 420/429."""

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = max(3, min(60, int(timeout or 15)))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
    ) -> tuple[Any, dict[str, str]]:
        url = f"{ESI_BASE}{path}"
        query = {"datasource": "tranquility"}
        if params:
            query.update(params)
        headers = {
            "Accept": "application/json",
            "User-Agent": "astrbot-eve-market/1.0 (github.com/Xiaoju9/astrbot_plugin_eve_market)",
        }
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method,
                        url,
                        params=query,
                        json=payload,
                        headers=headers,
                    ) as response:
                        if response.status in (420, 429):
                            await asyncio.sleep(2 + attempt * 2)
                            last_error = EsiError(f"ESI 限流（HTTP {response.status}）")
                            continue
                        if response.status == 404:
                            return None, dict(response.headers)
                        if response.status >= 400:
                            text = await response.text()
                            raise EsiError(f"ESI HTTP {response.status}: {text[:180]}")
                        data = await response.json()
                        return data, dict(response.headers)
            except asyncio.TimeoutError as exc:
                last_error = exc
        raise EsiError("ESI 请求失败，请稍后再试") from last_error

    async def resolve_ids(self, name: str, language: str = "zh") -> list[dict[str, Any]]:
        data, _ = await self._request(
            "POST",
            "/universe/ids/",
            params={"language": language},
            payload=[name],
        )
        if not data:
            return []
        rows = data.get("inventory_types") or []
        return [row for row in rows if isinstance(row, dict) and row.get("id")]

    async def type_info(self, type_id: int) -> dict[str, Any] | None:
        data, _ = await self._request(
            "GET",
            f"/universe/types/{int(type_id)}/",
            params={"language": "zh"},
        )
        if not data:
            return None
        if not data.get("name"):
            data, _ = await self._request(
                "GET",
                f"/universe/types/{int(type_id)}/",
                params={"language": "en"},
            )
        return data if isinstance(data, dict) else None

    async def close(self) -> None:
        # Sessions are opened per request; kept for a clean plugin lifecycle.
        return None

    async def market_orders(
        self,
        type_id: int,
        region_id: int,
        max_pages: int,
    ) -> tuple[list[dict[str, Any]], int]:
        orders: list[dict[str, Any]] = []
        first, headers = await self._request(
            "GET",
            f"/markets/{int(region_id)}/orders/",
            params={"order_type": "all", "type_id": int(type_id), "page": 1},
        )
        if not isinstance(first, list):
            return [], 1
        orders.extend(first)
        try:
            pages = int(headers.get("X-Pages", "1"))
        except (TypeError, ValueError):
            pages = 1
        pages = max(1, min(int(max_pages or 1), pages))
        for page in range(2, pages + 1):
            data, _ = await self._request(
                "GET",
                f"/markets/{int(region_id)}/orders/",
                params={"order_type": "all", "type_id": int(type_id), "page": page},
            )
            if isinstance(data, list):
                orders.extend(data)
        return orders, pages


class EveMarketPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}
        self.enabled = _as_bool(self.config.get("enabled"), True)
        self.region_id = _as_int(self.config.get("region_id"), JITA_REGION_ID, 1, 2_000_000_000)
        self.station_id = _as_int(self.config.get("station_id"), JITA_STATION_ID, 0, 2_000_000_000)
        self.station_only = _as_bool(self.config.get("station_only"), True)
        self.max_pages = _as_int(self.config.get("max_pages"), 10, 1, 50)
        self.cache_ttl = _as_int(self.config.get("cache_ttl"), 300, 0, 86400)
        self.request_timeout = _as_int(self.config.get("request_timeout"), 15, 3, 60)
        self.allow_bare = _as_bool(self.config.get("allow_bare_command"), True)
        self.client = EsiClient(self.request_timeout)
        self.last_error = ""
        self.name_index: dict[str, tuple[int, str, str]] = {}
        self._load_name_index()
        try:
            self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        except TypeError:
            self.data_dir = Path(StarTools.get_data_dir())
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "market.db"
        self._init_db()
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/status", self.api_status, ["GET"], "EVE market status"
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/cache/clear", self.api_cache_clear, ["POST"], "Clear price cache"
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/settings/save", self.api_settings_save, ["POST"], "Save plugin settings"
        )
        self.context.register_web_api(
            f"/{PLUGIN_NAME}/test", self.api_test, ["POST"], "Test a market query"
        )
        logger.info("[EveMarket] loaded; db=%s station=%s", self.db_path, self.station_id)

    # ------------------------------------------------------------------ db
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                create table if not exists items (
                    type_id integer primary key,
                    name_zh text not null default '',
                    name_en text not null default '',
                    group_id integer,
                    volume real,
                    updated_at text not null
                );
                create table if not exists price_cache (
                    cache_key text primary key,
                    payload text not null,
                    expires_at real not null
                );
                """
            )

    # ------------------------------------------------------------------ names
    def _save_item(self, info: dict[str, Any]) -> MarketItem:
        type_id = int(info["type_id"] if "type_id" in info else info.get("id") or 0)
        name_zh = str(info.get("name") or "")
        item = MarketItem(
            type_id=type_id,
            name_zh=name_zh,
            name_en=str(info.get("name_en") or ""),
            group_id=info.get("group_id"),
            volume=info.get("volume"),
        )
        with self._connect() as con:
            con.execute(
                """
                insert into items(type_id, name_zh, name_en, group_id, volume, updated_at)
                values(?,?,?,?,?,?)
                on conflict(type_id) do update set
                    name_zh=excluded.name_zh, name_en=excluded.name_en,
                    group_id=excluded.group_id, volume=excluded.volume,
                    updated_at=excluded.updated_at
                """,
                (item.type_id, item.name_zh, item.name_en, item.group_id, item.volume, _now()),
            )
        return item

    def _item_from_db(self, type_id: int) -> MarketItem | None:
        with self._connect() as con:
            row = con.execute("select * from items where type_id=?", (int(type_id),)).fetchone()
        if not row:
            return None
        return MarketItem(
            type_id=int(row["type_id"]),
            name_zh=str(row["name_zh"] or ""),
            name_en=str(row["name_en"] or ""),
            group_id=row["group_id"],
            volume=row["volume"],
        )

    def _load_name_index(self) -> None:
        """Load the compact SDE Chinese/English type-name index.

        ESI's ``/universe/ids`` endpoint does not return inventory types for
        ``language=zh`` (it only returns characters/corps/alliances), so the
        Chinese names have to be resolved locally before falling back to ESI.
        """
        path = Path(__file__).resolve().parent / "data" / "type_names.json"
        if not path.exists():
            logger.warning("[EveMarket] type name index missing: %s", path)
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("[EveMarket] failed to load type name index: %s", exc)
            return
        index: dict[str, tuple[int, str, str]] = {}
        for key, names in raw.items():
            try:
                type_id = int(key)
            except (TypeError, ValueError):
                continue
            zh = str(names[0] or "") if isinstance(names, list) and names else ""
            en = str(names[1] or "") if isinstance(names, list) and len(names) > 1 else ""
            for name in (zh, en):
                norm = normalize_name(name)
                if norm:
                    index.setdefault(norm, (type_id, zh, en))
        self.name_index = index
        logger.info("[EveMarket] loaded %s type names", len(index))

    def _item_from_local_name(self, norm: str) -> MarketItem | None:
        hit = self.name_index.get(norm)
        if not hit:
            return None
        type_id, name_zh, name_en = hit
        return MarketItem(type_id=type_id, name_zh=name_zh, name_en=name_en)

    async def _resolve_item(self, raw_name: str) -> MarketItem:
        raw_name = clean_message_text(str(raw_name or "")).strip()
        if not raw_name:
            raise ValueError("请告诉我要查什么物品。")
        norm = normalize_name(raw_name)

        local = self._item_from_local_name(norm)
        if local:
            self._save_item(
                {
                    "type_id": local.type_id,
                    "name": local.name_zh,
                    "name_en": local.name_en,
                }
            )
            return local

        with self._connect() as con:
            exact = con.execute(
                "select type_id from items where lower(name_zh)=? or lower(name_en)=? limit 1",
                (raw_name.lower(), raw_name.lower()),
            ).fetchone()
        if exact:
            item = self._item_from_db(int(exact["type_id"]))
            if item:
                return item

        for language in ("zh", "en"):
            rows = await self.client.resolve_ids(raw_name, language=language)
            if rows:
                info = await self.client.type_info(int(rows[0]["id"]))
                if info:
                    return self._save_item(info)

        raise ValueError(
            f"没找到「{raw_name}」。只支持游戏内完整名称，中文或英文都可以。"
        )

    # ------------------------------------------------------------------ prices
    def _cache_get(self, key: str) -> dict[str, Any] | None:
        if self.cache_ttl <= 0:
            return None
        with self._connect() as con:
            row = con.execute(
                "select payload, expires_at from price_cache where cache_key=?", (key,)
            ).fetchone()
        if not row or float(row["expires_at"]) < time.time():
            return None
        try:
            return json.loads(row["payload"])
        except (TypeError, ValueError):
            return None

    def _cache_set(self, key: str, payload: dict[str, Any]) -> None:
        if self.cache_ttl <= 0:
            return
        with self._connect() as con:
            con.execute(
                """
                insert into price_cache(cache_key, payload, expires_at) values(?,?,?)
                on conflict(cache_key) do update set
                    payload=excluded.payload, expires_at=excluded.expires_at
                """,
                (key, json.dumps(payload, ensure_ascii=False), time.time() + self.cache_ttl),
            )

    async def _summary_for(self, item: MarketItem) -> tuple[PriceSummary, bool]:
        is_plex = item.type_id == PLEX_TYPE_ID
        region_id = PLEX_REGION_ID if is_plex else self.region_id
        station = None if is_plex else (self.station_id if self.station_only else None)
        key = f"{item.type_id}:{region_id}:{station}:{self.max_pages}"
        cached = self._cache_get(key)
        if cached:
            return PriceSummary(**cached), True

        orders, pages = await self.client.market_orders(
            item.type_id, region_id, self.max_pages
        )
        summary = summarize_orders(orders, station_id=station, pages=pages)
        if station is not None and summary.sell_min is None and summary.buy_max is None:
            summary = summarize_orders(orders, station_id=None, pages=pages)
            summary.used_station = False
        self._cache_set(key, summary.as_dict())
        return summary, False

    async def query(self, args: str) -> str:
        item_name, quantity = parse_command_args(args)
        if not item_name:
            return self.help_text()
        item = await self._resolve_item(item_name)
        if item.type_id == PLEX_TYPE_ID and not has_explicit_quantity(args):
            quantity = PLEX_DEFAULT_QUANTITY
        summary, from_cache = await self._summary_for(item)
        if item.type_id == PLEX_TYPE_ID:
            label = f"{PLEX_REGION_NAME}（PLEX）"
        else:
            label = JITA_STATION_NAME if summary.used_station else "吉他星域"
        source = "宁静官方 ESI（缓存）" if from_cache else "宁静官方 ESI"
        return format_price(
            item,
            summary,
            quantity=quantity,
            station_label=label,
            fetched_at=datetime.now(timezone.utc),
            source_note=source,
        )

    def help_text(self) -> str:
        names = self.command_names()
        first = names[0] if names else "查价"
        return (
            f"用法：{first} <物品全名> [数量]\n"
            f"例如：{first} 乌鸦级\n"
            f"{first} Raven 10\n"
            f"{first} PLEX\n"
            "只支持游戏内完整名称（中文/英文），不支持别名。"
        )

    def command_names(self) -> list[str]:
        raw = str(self.config.get("command_names") or DEFAULT_COMMANDS)
        names = [part.strip() for part in re.split(r"[,，\s]+", raw) if part.strip()]
        return list(dict.fromkeys(names))[:20]

    def command_prefixes(self) -> set[str]:
        raw = str(self.config.get("command_prefixes") or "/!#")
        return {char for char in raw if not char.isspace()}

    # ------------------------------------------------------------------ chat
    def _match_command(self, text: str) -> tuple[str, str] | None:
        text = clean_message_text(str(text or ""))
        if not text:
            return None
        at_pattern = r"^(?:(?:@\S+)|(?:\[At:[^\]]+\]))\s*"
        addressed = bool(re.match(at_pattern, text))
        text = re.sub(at_pattern, "", text).strip()
        text = clean_message_text(text)
        prefixes = self.command_prefixes()
        had_prefix = addressed
        while text and text[0] in prefixes:
            had_prefix = True
            text = text[1:].lstrip()
        if not text:
            return None
        if not had_prefix and not self.allow_bare:
            return None
        first, _, rest = text.partition(" ")
        first_norm = first.casefold()
        for name in self.command_names():
            if first_norm == name.casefold():
                return name, rest.strip()
        return None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=20)
    async def on_market_message(self, event: AstrMessageEvent):
        if not self.enabled:
            return
        try:
            text = event.get_message_str()
        except Exception:
            text = getattr(event, "message_str", "")
        matched = self._match_command(str(text or ""))
        if not matched:
            return
        _, args = matched
        event.stop_event()
        event.set_extra("command_bare", True)
        if not args:
            yield event.plain_result(self.help_text())
            return
        try:
            reply = await self.query(args)
        except (EsiError, ValueError) as exc:
            reply = f"查价失败：{exc}"
        except Exception as exc:  # noqa: BLE001 - report, don't kill the handler
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("[EveMarket] query failed: %s", exc)
            reply = "查价失败了，ESI 或物品名可能有问题；稍后再试一次。"
        yield event.plain_result(reply[:1800])

    # ------------------------------------------------------------------ web
    def stats(self) -> dict[str, int]:
        with self._connect() as con:
            items = con.execute("select count(*) from items").fetchone()[0]
            cached = con.execute(
                "select count(*) from price_cache where expires_at >= ?", (time.time(),)
            ).fetchone()[0]
        return {"items": int(items), "cached_prices": int(cached)}

    async def api_status(self):
        return json_response(
            {
                "ok": True,
                "enabled": self.enabled,
                "commands": self.command_names(),
                "prefixes": "".join(sorted(self.command_prefixes())),
                "region_id": self.region_id,
                "station_id": self.station_id,
                "station_only": self.station_only,
                "station_label": JITA_STATION_NAME if self.station_only else "吉他星域",
                "max_pages": self.max_pages,
                "cache_ttl": self.cache_ttl,
                "stats": self.stats(),
                "db_path": str(self.db_path),
                "last_error": self.last_error,
            }
        )

    async def api_cache_clear(self):
        with self._connect() as con:
            con.execute("delete from price_cache")
        return json_response({"ok": True})

    async def api_settings_save(self):
        payload = await request.json(default={})
        mapping: dict[str, Any] = {}
        if "enabled" in payload:
            mapping["enabled"] = _as_bool(payload.get("enabled"), True)
        if "command_names" in payload:
            names = str(payload.get("command_names") or "").strip()
            if names:
                mapping["command_names"] = names
        if "station_only" in payload:
            mapping["station_only"] = _as_bool(payload.get("station_only"), True)
        if "station_id" in payload:
            mapping["station_id"] = _as_int(payload.get("station_id"), JITA_STATION_ID, 0, 2_000_000_000)
        if "region_id" in payload:
            mapping["region_id"] = _as_int(payload.get("region_id"), JITA_REGION_ID, 1, 2_000_000_000)
        if "cache_ttl" in payload:
            mapping["cache_ttl"] = _as_int(payload.get("cache_ttl"), 300, 0, 86400)
        if "max_pages" in payload:
            mapping["max_pages"] = _as_int(payload.get("max_pages"), 10, 1, 50)
        self.config.update(mapping)
        self.enabled = _as_bool(self.config.get("enabled"), True)
        self.station_only = _as_bool(self.config.get("station_only"), True)
        self.station_id = _as_int(self.config.get("station_id"), JITA_STATION_ID, 0, 2_000_000_000)
        self.region_id = _as_int(self.config.get("region_id"), JITA_REGION_ID, 1, 2_000_000_000)
        self.cache_ttl = _as_int(self.config.get("cache_ttl"), 300, 0, 86400)
        self.max_pages = _as_int(self.config.get("max_pages"), 10, 1, 50)
        try:
            saver = getattr(self.config, "save_config_async", None)
            if saver:
                await saver()
            else:
                self.config.save_config()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[EveMarket] save config failed: %s", exc)
            return error_response(f"配置已生效，但保存失败：{exc}", status_code=500)
        return json_response({"ok": True})

    async def api_test(self):
        payload = await request.json(default={})
        text = str(payload.get("query") or "").strip()
        if not text:
            return error_response("请输入要测试的物品", status_code=400)
        try:
            reply = await self.query(text)
        except (EsiError, ValueError) as exc:
            return error_response(str(exc), status_code=400)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[EveMarket] test failed: %s", exc)
            return error_response("查询失败，请查看 AstrBot 日志", status_code=500)
        return json_response({"ok": True, "reply": reply})

    async def terminate(self):
        try:
            await self.client.close()
        except Exception:
            pass
