# 字幕引擎手册 - `app/services/subtitle/engine.py`

> 路径：`backend/app/services/subtitle/engine.py`

---

## 一、模块概述

**SubtitleEngine** 对接 OpenSubtitles API v1，核心特性：
1. 简体中文优先评分系统
2. 本地字幕检测（已有则跳过，节省配额）
3. 听障字幕自动过滤
4. 429 限流冷却处理（等待 15 秒重试）
5. AI 字幕命名规范（`.ai.zh-CN.srt`）

---

## 二、语言评分系统

| 语言代码 | 评分 |
|---|---|
| `zh-CN` / `zh-cn` | 100 |
| `zh` | 90 |
| `zh-TW` / `zh-tw` | 50 |
| `zh-HK` / `zh-hk` | 40 |
| `en` | 30 |

---

## 三、主入口：`download_subtitle_for_task(...)` （异步）

**处理流程：**
1. 确定落盘目录（优先 `target_path` 所在目录，即媒体库）
2. **本地检测**：目录下已有同名 `.srt`/`.ass` 则直接跳过
3. 构建搜索参数（电影用 IMDB ID，剧集用 TMDB ID + 季集）
4. 调用 OpenSubtitles `/subtitles` 搜索
5. 过滤听障字幕，按评分排序选最优
6. 调用 `/download` 获取下载链接并落盘
7. 更新 `db_manager.update_archive_sub_status()`

**返回值：**
- `"跳过: 本地已有字幕"`
- `"成功: movie.ai.zh-CN.srt"`
- `"未找到中文字幕"`
- `"API 错误: ..."`

---

## 四、字幕命名规范

```
{video_stem}.ai.{lang_code}.srt
```

示例：`Dune.Part.Two.ai.zh-CN.srt` / `Frieren.S01E28.ai.zh-TW.srt`

---

## 五、`sub_status` 状态

| 状态 | 含义 |
|---|---|
| `pending` | 待查找 |
| `scraped` | 已成功下载 |
| `missing` | 未找到中文字幕 |
| `failed` | API 请求失败 |

---

## 六、注意事项

- `os_api_key` 存储 OpenSubtitles API Key，每日有下载配额限制
- 本地检测机制可有效节省配额
- 若调用方未传入 `season`/`episode`，自动从文件路径解析（支持 S01E05、1x05 格式）

---

*最后更新：2026-03-11*
