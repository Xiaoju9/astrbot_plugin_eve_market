# astrbot_plugin_eve_market

AstrBot 的 EVE Online 市场查价插件，第一版聚焦 **吉他 4-4（Jita IV - Moon 4）**。

## 功能

- 查吉他 4-4 的实时卖单最低价、收单最高价、中间价和挂单量
- **只认游戏内完整名称**：中文全名或英文全名，不做别名、不做模糊匹配
- 内置中文/英文物品名索引（本地 SDE，不依赖 ESI 的中文解析）
- 指令名可以自己改：`查价`、`市场`、`eve` 或任何你喜欢的名字
- 支持数量：`查价 乌鸦级 10`、`查价 乌鸦级 x10`
- 报价缓存，避免重复请求 ESI
- 后台页：查看状态、清缓存、测试查询、保存常用设置
- 查价输出不带 @/引用（配合 AstrBot 的 result decorate 或 command_bare 补丁）
- **PLEX 特殊处理**：自动查询 `GPMR-01` 市场；不填数量时按 500 计
- 输出格式对齐 `@yyyhf/koishi-plugin-evemarket2`

## 安装

把本目录放到：

```text
/opt/qq-stack/astrbot/data/plugins/astrbot_plugin_eve_market
```

重启 AstrBot，或在插件管理里重载。依赖只有 `aiohttp`（AstrBot 镜像一般已自带）。

## 使用

默认指令：

```text
查价 乌鸦级
市场 狞獾级海军型 10
eve Raven
查价 PLEX
/查价 乌鸦级
```

只查吉他 4-4；如果 4-4 完全没挂单，会自动回退到整个 Forge 星域，并在结果里标注。PLEX 固定查 GPMR-01，不回退。

输出示例：

```text
乌鸦级
 -出售：123,000,000 ISK（12）
 -收购：120,000,000 ISK（30）
 -中间：121,500,000 ISK
-----------------------
地点：吉他 4-4
数据来源：宁静官方 ESI
```

数量大于 1 时，会再显示一组总价：

```text
乌鸦级*10
 -出售：1,230,000,000 ISK
 -收购：1,200,000,000 ISK
 -中间：1,215,000,000 ISK
```

## 自定义

AstrBot 插件配置页可改：

| 配置 | 说明 | 默认 |
| --- | --- | --- |
| `command_names` | 指令名列表，逗号/空格分隔 | `查价,市场,eve` |
| `command_prefixes` | 允许的前缀 | `/!#` |
| `allow_bare_command` | 允许不带前缀 | `true` |
| `station_only` | 只查吉他 4-4 | `true` |
| `region_id` | 星域 ID | `10000002` |
| `station_id` | 空间站 ID | `60003760` |
| `max_pages` | ESI 订单最多翻页 | `10` |
| `cache_ttl` | 缓存秒数 | `300` |

后台页路径：

```text
http://127.0.0.1:6185/#/plugin-view/astrbot_plugin_eve_market/admin
```

## 名称规则

中文名和英文名都由本地 SDE 索引精确匹配。必须写游戏内完整名称：

```text
可以：乌鸦级、Raven、狞獾级海军型、Caracal Navy Issue、PLEX
不可以：乌鸦、大盾传、小乌鸦、海军神示
```

## 数据与限制

- 价格来自 [ESI](https://esi.evetech.net/) 的 `/markets/{region_id}/orders/`，不是本地估算。
- 第一版只围绕吉他；其他星域可以通过 `region_id` 改，但没有做多市场对比。
- PLEX（type_id 44992）不在 The Forge 挂单，插件固定查 `GPMR-01`（region 19000001）。
- 中文精确名由插件内置的 SDE 类型名索引解析（`data/type_names.json`）；ESI 的 `universe/ids` 不返回中文 inventory type。
- ESI 有速率限制；插件默认缓存 5 分钟，最多翻 10 页。
- 空间站市场（玩家建筑）需要 SSO 授权，第一版不做；只查 NPC 空间站/星域。

## 开发

```bash
python -m unittest discover -s tests -v
```

## License

MIT
