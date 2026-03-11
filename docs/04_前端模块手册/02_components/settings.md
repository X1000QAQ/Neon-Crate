# 设置面板组件 - `components/settings/`

---

## 一、`SettingsHub.tsx`（容器）

持有全局 `config` 状态，统一调度加载/保存。

**数据流：**
```
mount → api.getSettings() → config
config → props 传给各子 Tab 组件
子组件修改 → setConfig() 更新父层状态
点「保存配置」→ api.updateSettings(config)
```

**1+1 路径约束（保存前执行）：**
- 电影媒体库启用数 ≤ 1，剧集媒体库启用数 ≤ 1
- 有媒体库时两种类型必须同时存在

**约束验证 i18n key：**
- 配置冲突提示：`settings_config_conflict`
- 配置缺失提示：`settings_config_missing`

**Tab 列表：** basic / paths / api / inference / persona / regex

---

## 二、`BasicSettings.tsx`

| 配置项 | 说明 | i18n key |
|---|---|---|
| 界面语言 | `ui_lang` zh/en | `basic_interface` |
| 最小文件大小 | `min_size_mb`，扫描过滤阈值（MB）| `basic_min_size` |
| 定时巡逻开关 | `cron_enabled` | `basic_cron_enabled` |
| 巡逻间隔 | `cron_interval_min`（分钟）| `basic_cron_interval_min` |
| 自动化流水线开关 | `auto_process_enabled`（前端 UI 专用，控制子开关显隐）| `basic_auto_process_enabled` |
| 自动刮削 | `auto_scrape`（需先开启自动化流水线）| `basic_auto_scrape_label` |
| 自动找字幕 | `auto_subtitles`（需先开启自动化流水线）| `basic_auto_subtitles_label` |
| 在线/离线状态 | 动态显示 | `basic_online` / `basic_offline` |

**注意：** `auto_process_enabled` 只控制 UI 显示，后端忽略；真正生效的是 `auto_scrape` 和 `auto_subtitles`。

---

## 三、`PathsSettings.tsx`

添加/删除/启用下载目录和媒体库目录。每条路径：`type` / `path` / `category`（movie/tv/mixed）/ `enabled`。

**i18n key 对照：**

| 元素 | i18n key |
|---|---|
| 约束区块标题 | `paths_constraint` |
| 路径标签 | `paths_path_label` |
| 分类标签 | `paths_category_label` |
| 删除按钮 | `paths_delete_btn` |
| 类型标签 | `paths_type_label` |
| 在线/离线 | `basic_online` / `basic_offline` |

---

## 四、`APISettings.tsx`

TMDB / OpenSubtitles / Radarr / Sonarr 密钥配置，`type="password"` 输入框，后端加密存储。

**i18n key 对照：**

| 区块 | i18n key |
|---|---|
| TMDB 标题 | `api_tmdb_section` |
| OpenSubtitles 标题 | `api_opensubtitles_section` |
| Radarr 标题 | `api_radarr_section` |
| Sonarr 标题 | `api_sonarr_section` |
| 信号区块 | `api_signal` |
| Radarr URL 占位符 | `api_radarr_url_placeholder` |
| Sonarr URL 占位符 | `api_sonarr_url_placeholder` |

---

## 五、`InferenceSettings.tsx`

LLM 推理配置：云端/本地切换，URL / Key / Model。

**i18n key 对照：**

| 元素 | i18n key |
|---|---|
| 信号区块 | `inference_signal` |
| 云端 URL 占位符 | `inference_cloud_url_placeholder` |
| 本地 URL 占位符 | `inference_local_url_placeholder` |
| 本地密钥占位符 | `inference_local_key_placeholder` |
| 云端模型占位符 | `inference_cloud_model_placeholder` |
| 本地模型占位符 | `inference_local_model_placeholder` |

---

## 六、`PersonaSettings.tsx`

| 元素 | 说明 | i18n key |
|---|---|---|
| 身份区块标题 | IDENTITY | `persona_identity` |
| AI 名称标签 | AI 助手名称 | `persona_ai_name` |
| 人格区块标题 | PERSONA | `persona_persona_section` |
| 人格标签 | 人格 System Prompt | `persona_persona` |
| 归档专家区块标题 | EXPERT_ARCHIVE | `persona_expert_archive_section` |
| 归档专家规则标签 | 归档专家规则 | `persona_expert_rules` |
| 总控中枢区块标题 | ROUTER | `persona_router_section` |
| 总控中枢规则标签 | 总控路由规则 | `persona_router_rules` |
| 信号区块标题 | SIGNAL | `persona_signal` |
| 重置确认 | 用户确认重置 | `persona_reset_confirm` |
| 重置成功 | 重置完成提示 | `persona_reset_success` |
| 重置按钮状态 | 重置中... | `persona_resetting` |

一键重置：`api.resetSettings('ai')` → 刷新 config。

---

## 七、`RegexLab.tsx`

正则清洗规则编辑器，管理 `filename_clean_regex` 配置字段。

**架构地位：** `filename_clean_regex` 是系统**全局唯一正则真相源**，`MediaCleaner`（扫描引擎）和刮削任务的前置清洗均从此读取，严禁在代码里硬编码任何过滤正则。

**功能：**
- 多行编辑：每行一条规则，`#` 开头为注释行，自动跳过
- 单条实时测试：输入测试文件名，高亮匹配命中区域 + 删除线预览清洗效果
- 一键重置：`api.resetSettings('regex')` 恢复 15 条工业默认规则
- 通过 `SettingsHub` 统一保存（`POST /tasks/settings`）

**UI 结构与 i18n key：**

| 区块 | i18n key | 说明 |
|---|---|---|
| 标题 | `regex_lab_title` | 正则配置与测试中心 |
| 描述 | `regex_lab_desc` | 调试说明文本 |
| 系统规则区块 | `regex_system_rules` | SYSTEM_RULES 标题 |
| 规则输入框标签 | `regex_filename_clean_regex` | 文件名清洗正则 |
| 测试信号区块 | `regex_test_signal` | TEST_SIGNAL 标题 |
| 测试文件名输入框 | `regex_test_filename` | 测试文件名 |
| 正则表达式输入框 | `regex_expression` | 正则表达式 |
| 测试按钮 | `regex_test_btn` | 测试正则 |
| 结果标题 | `regex_result_title` | 匹配结果 |
| 匹配成功 | `regex_match_ok` | 匹配成功 |
| 无匹配 | `regex_no_match` | 无匹配 |
| 错误提示 | `regex_error` | 正则表达式错误 |
| 预览说明 | `regex_preview_highlight` | 匹配预览（高亮部分将被删除）|
| 常用模式标题 | `regex_common_title` | 常用正则模式 |
| 重置按钮 | `btn_reset_defaults` | 重置为默认值 |
| 重置确认 | `regex_reset_confirm` | 重置确认对话框 |

**默认 15 条规则分类：**

| # | 类别 |
|---|---|
| 1 | 分辨率标签（1080p/4K/BluRay...）|
| 2 | 编码格式（x264/HEVC/AAC...）|
| 3 | 方括号技术标签（含压制组关键词）|
| 4 | 花括号标签 |
| 5 | 广告词 |
| 6 | 音视频特性（HDR/10bit/IMAX...）|
| 7 | 语言标签（中英/CHT/Cantonese...）|
| 8 | 制作组后缀（`-TEAM` 末尾）|
| 9 | 年份 |
| 10-14 | 季集标签（S01E01/Season/1x01/EP01/第X集）|
| 15 | 动漫番剧集数格式 |

**注意：** 用户修改后需重启后端才能生效（规则在 `MediaCleaner` 初始化时一次性编译）。

---

## 八、`NeuralPrimitives.tsx`

原子组件：`NeuralInput` / `NeuralTextarea` / `NeuralSection` / `NeuralSelect` / `NeuralToggle` / `NeuralCoreSwitch`。

---

## 九、国际化完整性检查

所有设置界面组件已完全国际化，支持中英文切换。详见 `lib/i18n.ts` 中的完整 key 列表。

**关键国际化原则：**
- 所有 UI 文本、占位符、确认对话框均使用 i18n key
- 无硬编码字符串（除代码注释外）
- 新增 UI 元素必须同时在 `zh` 和 `en` 字典中添加对应 key

---

*最后更新：2026-03-11*
