# SettingsHub — 设置中心

**文件路径**: `frontend/components/settings/SettingsHub.tsx`  
**组件类型**: `'use client'`

---

## 职责

系统设置的顶层容器，管理配置数据加载/保存，通过 Tab 导航切换六个子模块。

---

## Tab 结构

| Tab ID | 标签 | 图标 | 子组件 |
|--------|------|------|--------|
| `basic` | 基础设置 | `Settings` | `BasicSettings` |
| `paths` | 路径管理 | `FolderOpen` | `PathsSettings` |
| `api` | API 密钥 | `Key` | `APISettings` |
| `inference` | 推理引擎 | `Brain` | `InferenceSettings` |
| `persona` | AI 人格 | `Code` | `PersonaSettings` |
| `regex` | 正则实验室 | `FlaskConical` | `RegexLab` |

---

## 保存流程

```
1. 前端 1+1 路径约束校验
   └── 启用的 library 路径中 movie==1 && tv==1
2. setLang(config.settings.ui_lang)  ← 同步前端语言
3. api.updateSettings(config)         ← 保存到后端
4. setTimeout(() => window.location.reload(), 100)
```

---

## 路径约束规则（前端校验）

| 违规 | 报错 |
|------|------|
| 电影库或剧集库超过 1 个 | `settings_config_conflict` |
| 有启用库但缺少电影/剧集某一类 | `settings_config_missing` |

与后端 `settings_router.py` 双重校验对应。

---

## 子模块说明

| 子组件 | 核心配置 |
|--------|----------|
| `BasicSettings` | 语言 / 扫描阈值 / 定时巡逻 / 自动流水线 |
| `PathsSettings` | 下载路径 + 媒体库路径增删改（1+1 结构）|
| `APISettings` | TMDB / OpenSubtitles / Radarr / Sonarr Key |
| `InferenceSettings` | LLM Provider / 云端和本地 URL+Key+Model |
| `PersonaSettings` | AI 人格设定 / 归档规则 / 路由规则 |
| `RegexLab` | 正则规则编辑 + 实时预览测试 |

---

## 子组件 Props 规范

```typescript
interface SettingsTabProps {
  config: SettingsConfig;
  setConfig: (c: SettingsConfig) => void;
  t: (key: I18nKey) => string;
}
```
