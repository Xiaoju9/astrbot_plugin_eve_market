# astrbot_plugin_eve_market

AstrBot 的 EVE Online 市场查价插件，第一版聚焦 **吉他 4-4（Jita IV - Moon 4）**。

## 功能

- 查吉他 4-4 的实时卖单最低价、收单最高价、价差、挂单量
- 支持中文名、英文名和自定义别名
- 内置中文物品名索引（本地 SDE，不依赖 ESI 的中文解析）
- 内置常用口语别名：大盾传 / 中盾传 / 小盾传 / 大盾扩 / 小盾扩 / 海军神示 / 乌鸦
- 指令名可以自己改：`查价`、`市场`、`eve` 或任何你喜欢的名字
- 支持数量：`查价 乌鸦级 10`、`查价 乌鸦级 x10`
- 报价缓存，避免重复请求 ESI
- 后台页：查看状态、管理别名、清缓存、测试查询、保存常用设置
- 查价输出不带 @/引用（配合 AstrBot 的 result decorate 或 command_bare 补丁）

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
市场 乌鸦级 10
eve 大盾传 x5
/查价 乌鸦级
```

只查吉他 4-4；如果 4-4 完全没挂单，会自动回退到整个 Forge 星域，并在结果里标注。

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
| `extra_aliases` | 额外别名，一行一个 `别名=物品名` | 空 |

后台页路径：

```text
http://127.0.0.1:6185/#/plugin-view/astrbot_plugin_eve_market/admin
```

## 别名

中文名由本地 SDE 索引精确匹配；口语/错别字需要别名或后台补充。内置别名可以后台覆盖，也可以追加：

```text
大盾传=Large Remote Shield Booster II
小乌鸦=乌鸦级
```

添加别名时，目标可以是物品名，也可以是 ESI type_id。

## 数据与限制

- 价格来自 [ESI](https://esi.evetech.net/) 的 `/markets/{region_id}/orders/`，不是本地估算。
- 第一版只围绕吉他；其他星域可以通过 `region_id` 改，但没有做多市场对比。
- 中文精确名由插件内置的 SDE 类型名索引解析（`data/type_names.json`）；ESI 的 `universe/ids` 不返回中文 inventory type。
- ESI 有速率限制；插件默认缓存 5 分钟，最多翻 10 页。
- 空间站市场（玩家建筑）需要 SSO 授权，第一版不做；只查 NPC 空间站/星域。

## 开发

```bash
python -m unittest discover -s tests -v
```

## License

MIT
