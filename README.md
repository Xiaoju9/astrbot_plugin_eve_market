<div align="center">

<img src="logo.png" width="120" alt="EVE Market logo">

# EVE Market · AstrBot 查价插件

只认游戏内完整物品名，查 **吉他 4-4** 的 ESI 实时买卖价。

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16.0-5B8DEF)](https://astrbot.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.2.0-blue)](https://github.com/Xiaoju9/astrbot_plugin_eve_market)

[功能](#功能) · [安装](#安装) · [使用](#使用) · [配置](#配置) · [实现](#实现) · [限制](#限制) · [开发](#开发)

</div>

---

## 简介

`eve_market` 是一个给 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 用的 EVE Online 市场查价插件。

它不做本地估价，也不让模型“凭印象报价”：每次查询都直接请求 **ESI 公开市场订单**，按空间站过滤后给出卖单最低价、收单最高价、中间价和挂单量。

项目最初是为了替代旧的 `ojita` 查价方式，现在的设计目标是：

- **准**：价格来自 ESI，不靠模型记忆。
- **窄**：只认游戏内完整名称，不猜别名。
- **轻**：一个 Python 插件 + 一个本地名称索引，不需要 Koishi、浏览器或 SSO。
- **可维护**：核心逻辑和 AstrBot 适配层分开，方便单测和二次开发。

## 功能

| 功能 | 说明 |
| --- | --- |
| 吉他 4-4 实时价格 | 查询 Jita IV - Moon 4（station `60003760`）的卖单和收单 |
| 星域回退 | 4-4 完全没挂单时，自动改用整个 The Forge 星域聚合 |
| 精确名称 | 中文全名、英文全名均可；不做别名、不做模糊匹配 |
| 本地名称索引 | 内置 SDE 类型名，约 5.4 万条，支持中英文 |
| 数量查询 | `乌鸦级*500`、`乌鸦级 x500`、`乌鸦级 500` |
| PLEX | 自动查 `GPMR-01`（type `44992`），默认按 500 个计算 |
| 输出格式 | 对齐 `@yyyhf/koishi-plugin-evemarket2` 的纯文本样式 |
| 自动 @ | 由 AstrBot 的 `reply_with_mention` 控制，回复时 @ 查询者 |
| 报价缓存 | 默认 5 分钟，减少 ESI 请求 |
| 后台管理 | 查看状态、测试查询、修改配置、清理缓存 |
| 自定义指令 | `查价`、`市场`、`eve` 或你喜欢的名字 |

## 安装

### 环境要求

- AstrBot **>= 4.16.0**
- Python **>= 3.10**
- 平台：`aiocqhttp` / OneBot v11
- 依赖：`aiohttp>=3.9`（AstrBot 镜像通常已自带）

### 手动安装

进入 AstrBot 的插件目录（不同部署方式路径可能不同）：

```bash
cd /path/to/astrbot/data/plugins
git clone https://github.com/Xiaoju9/astrbot_plugin_eve_market.git eve_market
```

确认目录结构是：

```text
data/plugins/eve_market/
├── main.py
├── market_core.py
├── metadata.yaml
├── logo.png
├── data/type_names.json
└── views/admin/
```

如果 AstrBot 没有自动安装依赖：

```bash
pip install -r requirements.txt
```

然后重启 AstrBot，或在插件管理页重载插件。

### 升级

```bash
cd /path/to/astrbot/data/plugins/eve_market
git pull
```

重启 AstrBot 生效。

## 使用

默认指令：

```text
查价 乌鸦级
查价 Raven
市场 狞獾级海军型 10
eve 狞獾级海军型*500
/查价 PLEX
```

### 名称规则

只接受游戏内完整名称，中文或英文都可以：

```text
可以：乌鸦级、Raven、狞獾级海军型、Caracal Navy Issue、PLEX
不可以：乌鸦、大盾传、小乌鸦、海军神示
```

这是刻意的设计：EVE 的物品名、舰船型别和装备型号非常容易混淆，模糊匹配会把“猜”带回来。名称不完整时，插件会直接提示“没找到”，不会拿相似物品的价格糊弄。

### 数量

数量写在物品名后面，支持三种写法：

```text
查价 狞獾级海军型*500
查价 狞獾级海军型 x500
查价 狞獾级海军型 500
```

数量大于 1 时，回复会先给单价，再给一组总价。

### PLEX

PLEX 不在 The Forge 的普通市场挂单，插件会自动查 **GPMR-01**：

```text
查价 PLEX
查价 PLEX*500
```

不写数量时按 **500 个**计算。

### 输出示例

```text
@查询者
乌鸦级
 -出售：123,000,000 ISK（12）
 -收购：120,000,000 ISK（30）
 -中间：121,500,000 ISK
-----------------------
数据来源：宁静官方 ESI
```

数量大于 1 时追加：

```text
乌鸦级*10
 -出售：1,230,000,000 ISK
 -收购：1,200,000,000 ISK
 -中间：1,215,000,000 ISK
```

> 回复里的 `@查询者` 由 AstrBot 的 `reply_with_mention` 控制。
> 如果不想引用回复，把 AstrBot 全局配置里的 `reply_with_quote` 设为 `false`。

## 配置

在 AstrBot 的插件配置页修改，或编辑插件配置项：

| 配置 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 启用插件 |
| `command_names` | string | `查价,市场,eve` | 指令名，逗号或空格分隔 |
| `command_prefixes` | string | `/!#` | 允许的指令前缀 |
| `allow_bare_command` | bool | `true` | 允许不带前缀直接发指令 |
| `station_only` | bool | `true` | 只查吉他 4-4；关闭则查整个 The Forge |
| `region_id` | int | `10000002` | 星域 ID（The Forge） |
| `station_id` | int | `60003760` | 空间站 ID（Jita 4-4） |
| `max_pages` | int | `10` | ESI 订单最多翻页数 |
| `cache_ttl` | int | `300` | 报价缓存秒数，`0` 表示不缓存 |
| `request_timeout` | int | `15` | ESI 请求超时秒数 |

### 后台页

登录 AstrBot 后台后打开：

```text
http://127.0.0.1:6185/#/plugin-view/eve_market/admin
```

端口以你的 AstrBot WebUI 实际地址为准。

后台页支持：

- 查看插件状态、物品索引数量和 ESI 配置
- 测试物品名与价格查询
- 修改指令名、缓存、空间站等设置
- 清除报价缓存

## 实现

```text
用户消息
  → 指令匹配（可配置前缀 / 指令名）
  → 本地 SDE 名称索引精确解析 type_id
  → ESI /markets/{region_id}/orders/?type_id=...
  → 按空间站或星域过滤
  → 卖单最低价 / 收单最高价 / 中间价 / 挂单量
  → 纯文本回复（AstrBot 负责 @）
```

关键点：

- **名称索引**：`data/type_names.json` 由 SDE 生成，保存 `type_id -> [中文名, 英文名]`。ESI 的 `universe/ids` 不返回中文 inventory type，所以不能只靠 ESI 解析中文名。
- **价格**：只使用公开 ESI 市场订单接口，不读本地缓存价，不做历史均价估算。
- **PLEX**：`type_id=44992`，市场区域固定为 `19000001`（GPMR-01）。
- **缓存**：SQLite 保存短期报价，默认 5 分钟；缓存 key 包含物品、星域、空间站和翻页上限。
- **@ 查询者**：插件只返回纯文本，由 AstrBot 的 `reply_with_mention` 统一加 @，避免和核心重复 @。

## 限制

- **不查玩家建筑市场**：结构市场需要 EVE SSO 授权和 `esi-markets.structure_markets.v1` scope，第一版不做。
- **不做多市场比价**：第一版围绕吉他；其他星域只能通过 `region_id` 改，没有“最低价在哪个 hub”的对比。
- **不做历史价格**：只查当前挂单，不画 K 线，不预测。
- **只认完整名称**：不提供别名、拼音、简称和模糊搜索，这是有意的取舍。
- **依赖公开 ESI**：ESI 限流或维护时会查价失败；插件有缓存，但不保证始终可用。
- **仅 aiocqhttp**：当前只声明支持 OneBot v11；其他平台需要自行适配消息组件。

## 开发

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

- 名称规范化与 `[MSG_ID]` / CQ 残留清理
- 数量解析（含 `物品*500` 紧凑写法）
- 空间站过滤、买卖盘聚合、ESI `volume_remain` 字段
- 输出格式（不含地点、包含数据来源）

仓库结构：

```text
eve_market/
├── main.py                 # AstrBot 插件入口、ESI 客户端、后台 API
├── market_core.py          # 纯 Python 市场逻辑，可独立测试
├── metadata.yaml           # AstrBot 插件元数据
├── _conf_schema.json       # 插件配置 schema
├── data/type_names.json    # 本地 SDE 名称索引
├── views/admin/            # 后台管理页
├── tests/                  # 单元测试
└── .github/workflows/      # CI
```

欢迎提 Issue 和 PR。提交前请先跑一遍单元测试，并尽量保持 `market_core.py` 不依赖 AstrBot，方便复用和测试。

## License

[MIT](LICENSE) © 2026 Xiaoju9

EVE Online 是 CCP hf. 的商标。本项目是非官方工具，与 CCP 无关，只使用公开 ESI 数据，不保存 EVE 账号、SSO token 或玩家建筑权限。
