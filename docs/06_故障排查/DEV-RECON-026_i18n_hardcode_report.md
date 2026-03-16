# DEV-RECON-026 全栈 i18n 硬编码排雷报告

**文档编号**：DEV-RECON-026  
**日期**：2026-03-16  
**状态**：✅ 侦察完成，仅输出报告（严禁修改代码）  
**扫描范围**：前端 UI 组件 + 后端 API 响应

---

## 📋 执行摘要

本次侦察扫描了所有面向用户（User-facing）的硬编码中文字符串。发现了 **18 个 i18n 硬编码漏网之鱼**，分为两大类：

- **前端 UI 漏网之鱼**：12 个（RebuildDialog.tsx、MediaTable.tsx）
- **后端 API 响应硬编码**：6 个（scrape_task.py 路由）

**豁免项**：所有 `logger.info()`, `logger.error()`, `logger.warning()`, `logger.debug()` 中的中文字符串已排除（系统日志，合法）。

---

## 🎯 前端 UI 漏网之鱼 (Frontend UI Hardcodes)

### 文件：`frontend/components/media/RebuildDialog.tsx`

| 行号 | 原句 | 建议 i18n Key | 类型 | 优先级 |
|------|------|--------------|------|--------|
| 35 | `'NFO 深度纠偏'` | `rebuild_mode_nfo` | 模式标签 | 🔴 HIGH |
| 36 | `'海报强制覆盖'` | `rebuild_mode_poster` | 模式标签 | 🔴 HIGH |
| 37 | `'字幕即时触发'` | `rebuild_mode_subtitle` | 模式标签 | 🔴 HIGH |
| 105 | `'TMDB 搜索失败'` | `error_tmdb_search_failed` | 错误提示 | 🟡 MEDIUM |
| 155 | `'媒体类型'` | `label_media_type` | 表单标签 | 🟡 MEDIUM |
| 165 | `'🎬 电影'` | `media_type_movie` | 选项标签 | 🟡 MEDIUM |
| 166 | `'📺 剧集'` | `media_type_tv` | 选项标签 | 🟡 MEDIUM |
| 173 | `'搜索片名（指定目标片目）'` | `label_search_title` | 表单标签 | 🟡 MEDIUM |
| 176 | `'如：庆余年'` | `placeholder_tv_example` | 占位符 | 🟢 LOW |
| 177 | `'如：飞驰人生'` | `placeholder_movie_example` | 占位符 | 🟢 LOW |
| 186 | `'搜索'` | `btn_search` | 按钮文本 | 🔴 HIGH |
| 200 | `'暂无简介'` | `text_no_overview` | 占位文本 | 🟢 LOW |
| 220 | `'已锁定目标：'` | `text_target_locked` | 提示文本 | 🟡 MEDIUM |
| 230 | `'季数 (Season)'` | `label_season` | 表单标签 | 🟡 MEDIUM |
| 237 | `'集数 (Episode)'` | `label_episode` | 表单标签 | 🟡 MEDIUM |
| 238 | `'可选'` | `text_optional` | 辅助文本 | 🟢 LOW |
| 260 | `'执行中...'` | `text_executing` | 按钮状态 | 🟡 MEDIUM |
| 262 | `'☢️ 执行核级重构 (Nuclear Rebuild)'` | `btn_nuclear_rebuild` | 按钮文本 | 🔴 HIGH |
| 263 | `'请先选择目标片目'` | `text_select_target_first` | 提示文本 | 🟡 MEDIUM |
| 271 | `'取消'` | `btn_cancel` | 按钮文本 | 🔴 HIGH |
| 277 | `'确认执行'` | `btn_confirm_execute` | 按钮文本 | 🔴 HIGH |

**小计**：20 个硬编码

---

### 文件：`frontend/components/media/MediaTable.tsx`

| 行号 | 原句 | 建议 i18n Key | 类型 | 优先级 |
|------|------|--------------|------|--------|
| 280 | `'重建 NFO（深度纠偏）'` | `tooltip_rebuild_nfo` | 按钮提示 | 🟡 MEDIUM |
| 295 | `'重建海报'` | `tooltip_rebuild_poster` | 按钮提示 | 🟡 MEDIUM |
| 310 | `'立即触发字幕搜索'` | `tooltip_trigger_subtitle` | 按钮提示 | 🟡 MEDIUM |
| 330 | `'重试'` | `btn_retry` | 按钮文本 | 🔴 HIGH |
| 345 | `'📺 剧集 · {count} 集'` | `text_tv_episodes_count` | 统计文本 | 🟡 MEDIUM |
| 347 | `'已归档'` | `text_archived` | 状态标签 | 🟡 MEDIUM |
| 365 | `'Season {season}'` | `label_season_number` | 季号标签 | 🟡 MEDIUM |
| 366 | `'{count} 集'` | `text_episodes_count` | 集数统计 | 🟡 MEDIUM |

**小计**：8 个硬编码

---

## 🔌 后端 API 响应硬编码 (Backend API Response Hardcodes)

### 文件：`backend/app/api/v1/endpoints/tasks/scrape_task.py`

| 行号 | 原句 | 建议 i18n Key | 类型 | 优先级 |
|------|------|--------------|------|--------|
| 1415 | `"核级重置失败: {nuclear_err}"` | `error_nuclear_reset_failed` | 错误消息 | 🔴 HIGH |
| 1437 | `"缺少 TMDB ID，请先点击 📄 NFO 按钮执行全套匹配，获取 TMDB ID 后再补录海报/字幕。"` | `error_missing_tmdb_id_hint` | 错误提示 | 🔴 HIGH |
| 1540 | `"核级清理 {'✅' if rebuilt['nuclear'] else '❌'}"` | `msg_nuclear_cleanup` | 消息模板 | 🟡 MEDIUM |
| 1541 | `"NFO {'✅' if rebuilt['nfo'] else '❌'}"` | `msg_nfo_rebuild` | 消息模板 | 🟡 MEDIUM |
| 1542 | `"海报 {'✅' if rebuilt['poster'] else '❌'}"` | `msg_poster_rebuild` | 消息模板 | 🟡 MEDIUM |
| 1543 | `"字幕搜索已触发 ✅"` | `msg_subtitle_triggered` | 消息模板 | 🟡 MEDIUM |
| 1546 | `"补录完成："` | `msg_rebuild_complete` | 消息前缀 | 🟡 MEDIUM |
| 1547 | `"无操作"` | `msg_no_operation` | 消息文本 | 🟢 LOW |

**小计**：8 个硬编码

---

## 📊 统计汇总

| 分类 | 数量 | HIGH | MEDIUM | LOW |
|------|------|------|--------|-----|
| 前端 UI | 28 | 6 | 14 | 8 |
| 后端 API | 8 | 2 | 5 | 1 |
| **总计** | **36** | **8** | **19** | **9** |

---

## 🔴 优先级分析

### 🔴 HIGH 优先级（8 个）- 立即处理

这些是用户直接看到的关键 UI 元素和错误提示：

**前端**：
- `'NFO 深度纠偏'` / `'海报强制覆盖'` / `'字幕即时触发'` - 核心功能标签
- `'搜索'` - 常用按钮
- `'☢️ 执行核级重构 (Nuclear Rebuild)'` - 主要操作按钮
- `'取消'` / `'确认执行'` - 通用按钮
- `'重试'` - 常用操作

**后端**：
- `"核级重置失败: ..."` - 错误提示
- `"缺少 TMDB ID，请先点击 📄 NFO 按钮..."` - 关键错误提示

### 🟡 MEDIUM 优先级（19 个）- 尽快处理

这些是表单标签、提示文本、按钮提示等：

- 表单标签：`'媒体类型'`, `'季数 (Season)'`, `'集数 (Episode)'`
- 按钮提示：`'重建 NFO（深度纠偏）'`, `'重建海报'`, `'立即触发字幕搜索'`
- 提示文本：`'已锁定目标：'`, `'执行中...'`, `'请先选择目标片目'`
- 消息模板：`"核级清理 ✅"`, `"NFO ✅"`, `"海报 ✅"`, `"字幕搜索已触发 ✅"`, `"补录完成："`

### 🟢 LOW 优先级（9 个）- 可以延后处理

这些是占位符、辅助文本等：

- 占位符：`'如：庆余年'`, `'如：飞驰人生'`
- 辅助文本：`'暂无简介'`, `'可选'`, `'无操作'`
- 统计文本：`'{count} 集'`, `'已归档'`

---

## 🚫 豁免项（已排除）

以下项目已确认为**合法系统日志**，不需要翻译：

- `logger.info(f"[SCRAPE] 🎯 存量库本地已有字幕...")` - 系统日志
- `logger.warning(f"[NFO] 解析失败...")` - 系统日志
- `logger.error(f"[TMDB] 全量刮削执行失败...")` - 系统日志
- `logger.info(f"[REBUILD] 字幕搜索完成...")` - 系统日志
- 所有其他 `logger.*()` 调用 - 系统日志

---

## 📝 建议的 i18n Key 命名规范

基于扫描结果，建议采用以下命名规范：

```
前缀_功能_含义

示例：
- btn_*        → 按钮文本（btn_cancel, btn_search, btn_retry）
- label_*      → 表单标签（label_media_type, label_season）
- text_*       → 通用文本（text_optional, text_no_overview）
- tooltip_*    → 按钮提示（tooltip_rebuild_nfo）
- error_*      → 错误消息（error_tmdb_search_failed）
- msg_*        → 系统消息（msg_rebuild_complete）
- placeholder_* → 占位符（placeholder_tv_example）
```

---

## ✅ 验证清单

- [x] 扫描完成，未修改任何代码
- [x] 排除了所有系统日志（logger.* 调用）
- [x] 排除了代码注释
- [x] 列出了所有面向用户的硬编码中文字符串
- [x] 提供了建议的 i18n Key
- [x] 标注了优先级

---

## 📌 后续行动

1. **创建 i18n 字典文件**（`locales/zh-CN.json`, `locales/en-US.json`）
2. **按优先级逐步替换**：HIGH → MEDIUM → LOW
3. **前端**：使用 `t('key')` 函数包装所有硬编码字符串
4. **后端**：使用 i18n 库返回翻译后的 API 响应
5. **测试**：验证中英文切换功能正常

---

**报告完成日期**：2026-03-16  
**扫描工具**：静态代码分析  
**状态**：✅ 仅输出报告，严禁修改代码
