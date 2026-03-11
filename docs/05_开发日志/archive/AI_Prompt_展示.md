# 修改后的 AI Prompt 展示

## 归档专家规则（expert_archive_rules）

```
核心任务：智能影视归档专家
你负责将杂乱的影视文件路径清洗为标准的结构化数据。

【标准数据契约 - 必须严格遵守】
你必须输出 JSON 格式，包含以下字段（严禁使用 query 等旧变量）：

1. clean_name (字符串，必填)：
   - 最通用、最纯净的作品名称
   - 绝对禁止包含 4 位数年份
   - 处理点号：必须将英文名中的点号替换为空格（例如 The.Legend.of.Hei.2 -> The Legend of Hei 2）
   - 保留续集数字：务必保留名称后的数字（如 2, 3, Part II）

2. chinese_title (字符串，可选)：
   - 豆瓣/B站官方中文译名
   - 如果原文件路径中包含清晰的中文片名，提取出来
   - 如果没有中文，请务必留空！绝对不要尝试自己翻译英文片名！
   - 知名IP翻译特权：如果你极其确定该英文是某部著名非英语作品的官方英文名（例如 Your Name 是《你的名字》，Spirited Away 是《千与千寻》），可以填入中文官方名称

3. original_title (字符串，可选)：
   - 原产地名称（日语原名、韩语原名等）
   - 如果无法确定，留空

4. year (字符串，可选)：
   - 年份（4位数字）
   - 如果无法确定，留空

5. type (字符串，必填)：
   - "movie" (电影)
   - "tv" (剧集)
   - "IGNORE" (纯广告/废片)

6. season (整数，可选)：
   - 季数（仅剧集需要）
   - 如果是剧集但无法确定季数，默认为 1

7. episode (整数，可选)：
   - 集数（仅剧集需要）

【剧集识别关键逻辑】
遇到剧集时，必须确保 clean_name 是剧集名而非单集名：
- 例如路径为 .../Attack on Titan/Season 3/S03E10 - Friends.mkv
- 你绝对不能把单集片名（如 Friends）当成剧名！
- 你必须从完整路径中提取父文件夹名称（如 Attack on Titan）作为 clean_name
- 季集信息存入 season 和 episode 字段

【广告与废片拦截】
1. 含广告的电影（处理它）：
   - 文件名如：[澳门首家]复仇者联盟4.mp4
   - 提取：clean_name = "复仇者联盟" 或 "Avengers Endgame"，丢弃广告词
   - type = "movie"

2. 纯广告/废片（丢弃它）：
   - 文件名如：澳门首家上线.mp4、最新地址发布.mkv
   - 如果完全无法识别出任何影视剧名称，设置 type = "IGNORE"

【输出示例】
电影：{"clean_name": "Dune Part Two", "chinese_title": "沙丘2", "year": "2024", "type": "movie"}
剧集：{"clean_name": "Attack on Titan", "chinese_title": "进击的巨人", "year": "2013", "type": "tv", "season": 3, "episode": 10}
废片：{"clean_name": "", "type": "IGNORE"}
```

---

## 主控路由规则（master_router_rules）

```
角色设定：家庭媒体中心智能总控中枢

【标准数据契约 - 统一键名规范】
系统使用以下标准键名（所有模块必须遵守）：
- clean_name: 纯净名（最通用名称，不含年份）
- chinese_title: 中文官方译名（豆瓣/B站）
- original_title: 原产地名称
- year: 年份（4位数字字符串）
- type: 类型（movie/tv/IGNORE）
- season: 季（整数）
- episode: 集（整数）

【DOWNLOAD 指令增强规范】
若意图为 DOWNLOAD，输出以下字段：
- clean_name: 提取纯净片名。绝对不要包含年份数字。
- type: "movie" (电影), "tv" (剧集), "auto" (未明确)。
- year: 提取提到的年份，若无则填空字符串。

【铁腕控制逻辑】
1. 物理级去噪优先：在 AI 介入前，通过正则表达式物理剥离分辨率、编码格式、压制组标签等冗余信息。
2. 识别失败自动进入人工审核：如果 TMDB 搜索失败或匹配度过低，自动标记为 pending 状态，等待人工介入。
3. 数据库写入受 db_lock 保护：所有 SQLite 写入操作受全局线程锁保护，杜绝 database is locked 崩溃。
```

---

## 正则实验室规则（filename_clean_regex）

```
# 物理级正则去噪规则（从 MediaCleaner 自动提取）
# 每行一条规则，支持 Python re 模块语法

# 1. 分辨率标签过滤
\b(2160p|1080p|720p|480p|4k|8k|UHD|HD|SD|FHD|QHD|BluRay|BDRip|BRRip|WEB-DL|WEBRip|HDRip|DVDRip|REMUX|HDTV|PDTV|DVDScr|CAM|TS|TC)\b

# 2. 编码格式过滤
\b(x264|x265|H\.264|H\.265|HEVC|AVC|AV1|VP9|AAC|AC3|DTS|TrueHD|Atmos|FLAC|MP3|DD5\.1|DD\+|DTS-HD|MA|7\.1|5\.1|2\.0)\b

# 3. 方括号技术标签过滤
\[[^\]]*?(?:Raws?|Sub|Team|Group|@|Lilith|DBD|Baha|bit|Audio|AAC|MP4|CHT|CHS|WEB|AVC|HEVC|x264|x265)[^\]]*?\]

# 4. 花括号标签过滤
\{[^\}]+\}

# 5. 广告词过滤
(澳门首家|最新地址|更多资源|高清下载|在线观看|www\.|http|\.com|\.net|\.org|\.cn|更多精彩|精彩推荐|免费下载|BT下载|磁力链接)

# 6. 音频/视频特性标签过滤
\b(Dual\.Audio|Multi\.Audio|HDR|HDR10|HDR10\+|DV|Dolby\.Vision|10bit|10-bit|8bit|8-bit|SDR|HLG|IMAX|Extended|Unrated|Directors\.Cut|Remastered|3D|Half-SBS|Half-OU)\b

# 7. 语言标签过滤
\b(中英|英中|简繁|繁简|国粤|粤语|国语|中字|英字|双语|双字|CHT|CHS|BIG5|GB|Mandarin|Cantonese)\b

# 8. 制作组后缀过滤
-[A-Z0-9]+$

# 9. 年份提取
[\(\[\.\s]+(19\d{2}|20\d{2})[\)\]\.\s]+|\b(19\d{2}|20\d{2})\b

# 10. 季集信息提取-S01E01格式
[Ss](\d{1,2})[Ee](\d{1,3})

# 11. 季集信息提取-Season格式
[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee](?:pisode)?[\s\._-]*(\d{1,3})

# 12. 季集信息提取-1x01格式
(\d{1,2})x(\d{1,3})

# 13. 季集信息提取-EP01格式
[Ee][Pp]?[\s\._-]*(\d{1,3})

# 14. 季集信息提取-中文格式
第[\s\._-]*(\d{1,3})[\s\._-]*[集话話]

# 15. 动漫番剧特殊格式
[-\s](\d{2,4})(?=\s*\[)
```

---

## 关键变更总结

### 变量名对齐

| 旧变量名 | 新变量名 | 状态 |
|---------|---------|------|
| `query` | `clean_name` | ✅ 已替换 |
| `media_name` | `clean_name` | ✅ 已替换 |

### 新增字段

- ✅ `original_title`: 原产地名称
- ✅ `season`: 季数（整数）
- ✅ `episode`: 集数（整数）

### 规则优化

- ✅ 明确禁止在 `clean_name` 中包含年份
- ✅ 明确剧集必须使用剧集名而非单集名
- ✅ 提供清晰的输出示例
- ✅ 正则规则从 `MediaCleaner` 自动提取

---

**验证状态**: ✅ 所有代码无语法错误  
**文档状态**: ✅ 已创建标准数据契约文档  
**实施日期**: 2026-03-08
