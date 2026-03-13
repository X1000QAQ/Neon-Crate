# page.tsx — 主页面（SPA 四视图）

**文件路径**: `frontend/app/page.tsx`  
**组件类型**: `'use client'`  
**路由**: `/`

---

## 职责

作为主应用入口，通过 `activeView` 状态在四个视图间切换，实现无路由跳转的 SPA 体验。

---

## 视图切换

```typescript
type View = 'dashboard' | 'media' | 'monitor' | 'settings';
const [activeView, setActiveView] = useState<View>('dashboard');
```

| activeView | 渲染组件 | 说明 |
|------------|---------|------|
| `dashboard` | `StatsOverview` + `MiniLog` | 仪表盘：统计卡片 + 指令中心 + 日志流 |
| `media` | `MediaWall` | 媒体库：完整任务列表管理 |
| `monitor` | `SystemMonitor` | 系统监控：实时日志 + 过滤器 |
| `settings` | `SettingsHub` | 系统设置：6 个配置 Tab |

---

## 顶栏导航

```
nav items = [
  { id: 'dashboard', label: t('nav_dashboard'), icon: LayoutDashboard },
  { id: 'media',     label: t('nav_task_list'), icon: Film },
  { id: 'monitor',   label: t('nav_monitor'),   icon: Activity },
  { id: 'settings',  label: t('nav_system_settings'), icon: Settings },
]
```

激活状态：`bg-cyber-cyan text-black`，非激活：透明 + 霓虹边框。

---

## 背景层结构

```
固定层（z-index）：
  -20  →  bg-main.jpg（物理壁纸底层）
  -10  →  radial-gradient 全息暗场蒙版 + backdropFilter: blur(3px)
    0  →  CyberParticles canvas（来自 ClientShell）
   10  →  实际页面内容
   50  →  顶部 Header
  100  →  AiSidebar
  110  →  AiSidebar 触发轴
```

---

## 关键 Hook

```typescript
const { t } = useLanguage();  // 国际化文本
```

---

## 依赖关系

```
page.tsx
  ├── components/media/StatsOverview
  ├── components/media/MiniLog
  ├── components/media/MediaWall
  ├── components/media/SystemMonitor
  ├── components/settings/SettingsHub
  ├── hooks/useLanguage
  └── lib/utils (cn)
```
