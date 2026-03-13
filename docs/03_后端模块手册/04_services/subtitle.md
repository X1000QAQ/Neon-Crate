# subtitle — 字幕引擎

**文件路径**: `backend/app/services/subtitle/engine.py`  
**核心类**: `SubtitleEngine`

---

## 职责

对接 OpenSubtitles API，搜索并下载简体中文字幕：
- 简体优先评分系统
- 听障字幕自动过滤
- 本地字幕检测（避免重复下载）
- 字幕落盘使用 AI 钢印命名

---

## 初始化

```python
engine = SubtitleEngine(
    api_key="your-opensubtitles-key",
    user_agent="SubtitleHunter/13.2"
)
```

---

## download_subtitle_for_task

```python
result = await engine.download_subtitle_for_task(
    db_manager=db,
    file_path="/downloads/movie.mkv",
    tmdb_id="123456",
    media_type="movie",
    imdb_id="tt1234567",
    target_path="/media/Movie (2021)/Movie (2021).mkv",
    archive_id=42
)
```

**执行流程**：

```
1. 检查目标目录是否已存在字幕 → 跳过（幂等）

2. 构建搜索参数
   电影: imdb_id 优先，无则 tmdb_id
   剧集: parent_imdb_id + parent_tmdb_id + season/episode

3. GET /subtitles（语言: zh,zh-cn,zh-tw,zh-hk）
   429 限流 → 冷却 15 秒后重试

4. 过滤听障字幕（hearing_impaired=true）

5. 评分排序（zh-CN=100 > zh=90 > zh-TW=50 > zh-HK=40）

6. POST /download 获取下载链接

7. 落盘：{video_stem}.ai.{lang}.srt
   如：Movie (2021).ai.zh-CN.srt

8. db.update_archive_sub_status(sub_status="scraped")
```

---

## sub_status 状态值

| 值 | 含义 |
|----|------|
| `"scraped"` | 字幕下载成功 |
| `"missing"` | 搜索无结果 / 仅有听障字幕 |
| `"failed"` | API 错误 / 下载链接获取失败 |

---

## 字幕命名规范

```
{video_stem}.ai.{lang_code}.srt

# 示例
Dune Part Two (2024).ai.zh-CN.srt
Attack on Titan (2013) - S03E10.ai.zh-TW.srt
```

`ai.` 钢印区分 AI 下载字幕与自带字幕，防止被 Jellyfin/Emby 覆盖。

---

## API 限流保护

- 搜索和下载请求均检测 `429`，自动 `await asyncio.sleep(15)`
- `subtitle_task.py` 中每条任务后 `time.sleep(1)` 额外保护
