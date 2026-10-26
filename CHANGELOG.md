# Changelog

All notable changes to this project are documented here.

## [1.2.0] - 2026-10-26

### Added

- EVE 吉他 4-4 市场查价：卖单最低价、收单最高价、中间价、挂单量。
- 本地 SDE 中英文完整名称索引，精确匹配，不依赖 ESI 中文名称。
- 数量查询：`物品*500`、`物品 x500`、`物品 500`。
- PLEX 自动查询 `GPMR-01`（`type_id 44992`），默认 500 个。
- AstrBot 后台管理页：状态、测试查询、配置、清缓存。
- 插件图标 `logo.png`。
- 单元测试与 GitHub Actions CI。

### Changed

- 回复格式对齐 `@yyyhf/koishi-plugin-evemarket2` 的纯文本样式。
- 回复通过 AstrBot 的 `reply_with_mention` @ 查询者。
- 移除了地点标注。
- 移除了全部别名/模糊匹配逻辑，只接受游戏内完整名称。
- 修复 OneBot `[MSG_ID:...]` 残留导致查不到物品的问题。
- 修复 `物品*500` 紧凑写法被当成物品名一部分的问题。

### Notes

- 第一版只支持 NPC 空间站/星域公开市场，不查询玩家建筑市场。
- 结构市场需要 EVE SSO 授权，后续版本再考虑。

## [1.1.0]

- 初始可用版本：Jita 4-4 查价、PLEX、后台页、自定义指令。
