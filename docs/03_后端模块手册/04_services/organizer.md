# organizer — 智能链接归档

**文件路径**: `backend/app/services/organizer/hardlinker.py`  
**核心类**: `SmartLink`

---

## 职责

将下载目录中的媒体文件以**零磁盘空间**的方式归档到媒体库：
- 首选硬链接（同分区，零额外空间）
- 跨分区自动回退软链接
- 字幕文件自动同步搬运

---

## SmartLink.create_link

```python
success, link_type = SmartLink.create_link(src, dst)
```

**返回值**：

| `link_type` | 含义 |
|-------------|------|
| `"hardlink"` | 硬链接创建成功 |
| `"symlink"` | 软链接（跨分区兜底）|
| `"already_exists"` | 目标已存在，视为幂等成功 |
| `"error: ..."` | 失败原因描述 |

**跨分区检测**：捕获 `errno.EXDEV`，自动切换为 `os.symlink()`。

**Windows 适配**：自动传入 `target_is_directory` 参数。

---

## SmartLink.sync_subtitles

```python
count = SmartLink.sync_subtitles(
    src_video_path,
    dest_video_path,
    dest_dir
)
```

自动搬运与视频同目录、以视频文件名为前缀的字幕文件（`.srt` `.ass` `.ssa` `.sub`）。

**平铺目录保护**：检测到公共下载大厅目录时跳过字幕扫描，防止跨片污染。

---

## SmartLink.get_link_type

```python
link_type = SmartLink.get_link_type(path)
# 返回: "hardlink" | "symlink" | "regular" | "not_exist"
```

通过 `stat().st_nlink > 1` 判断硬链接，`os.path.islink()` 判断软链接。

---

## 归档目录结构

**电影**：
```
{library_root}/
  {Title} ({Year})/
    {Title} ({Year}).mkv
    movie.nfo
    poster.jpg
    fanart.jpg
```

**剧集**：
```
{library_root}/
  {Title} ({Year})/
    tvshow.nfo
    poster.jpg
    Season 1/
      {Title} ({Year}) - S01E01.mkv
```

---

## 安全机制

路径穿越防护在 `scrape_task.py` 中执行（归档前校验）：

```python
Path(target_path).resolve().relative_to(Path(library_root).resolve())
# 失败则拦截，记录 SECURITY 日志，跳过该任务
```
