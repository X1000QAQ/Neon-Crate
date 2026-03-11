# 归档组织器手册 - `app/services/organizer/hardlinker.py`

> 路径：`backend/app/services/organizer/hardlinker.py`

---

## 一、模块概述

**SmartLink** 归档组织器，将视频文件从下载目录「搬运」到媒体库。优先硬链接（零额外空间），跨设备自动降级。

---

## 二、`SmartLink` 静态方法

### `create_link(src, dst) -> Tuple[bool, str]`

三级降级策略：

```
1. 硬链接 os.link()       # 同分区，零额外空间
   ↓ 失败（跨分区）
2. 软链接 os.symlink()    # 跨分区，依赖源文件存在
   ↓ 失败
3. 文件复制 shutil.copy2  # 兜底，占用双倍空间
```

返回 `(success: bool, link_type: str)`，`link_type` 为 `"hardlink"` / `"symlink"` / `"copy"`。

### `build_movie_path(library_root, title, year, filename) -> str`

```
{library_root}/{title} ({year})/{filename}
```

### `build_tv_path(library_root, title, year, season, filename) -> str`

```
{library_root}/{title} ({year})/Season {season:02d}/{filename}
```

### `ensure_dir(path)`

`Path(path).mkdir(parents=True, exist_ok=True)` 封装。

---

## 三、归档路径示例

**电影：**
```
/storage/movies/沙丘：第二部 (2024)/Dune.Part.Two.2024.mkv
```

**剧集：**
```
/storage/tv/葬送的芙莉莲 (2023)/Season 01/Frieren.S01E28.mkv
```

---

## 四、调用链

```
POST /tasks/scrape_all
  └─► SmartLink.build_movie_path() / build_tv_path()
        └─► SmartLink.create_link(src, dst)
              ├─► 硬链接成功 → db 更新 archived
              └─► 降级后成功 → db 更新 archived
```

---

## 五、注意事项

- 硬链接要求源文件和目标在**同一分区**，Docker 单存储挂载（`/storage`）可确保此条件
- 软链接归档后若删除源文件（下载目录清理），媒体库中的链接将失效
- `build_*_path()` 会对标题移除 `/` 等非法字符

---

*最后更新：2026-03-11*
