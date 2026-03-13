# globals.css — 全局样式

**文件路径**: `frontend/app/globals.css`

---

## 字体体系

| 字体 | 用途 | 来源 |
|------|------|------|
| `Advent Pro` | 全局正文 / 标题 / 按钮 | Google Fonts @import |
| `Hacked` | 密码框 / API Key / 终端代码 | Base64 嵌入 @font-face |

```css
body { font-family: 'Advent Pro', 'Orbitron', 'Segoe UI', sans-serif; }
input[type="password"] { font-family: 'Hacked', monospace !important; }
```

---

## CSS 变量（:root）

| 变量 | 值 | 说明 |
|------|-----|------|
| `--cyber-cyan` | `#00e6f6` | 霓虹青主色 |
| `--cyber-yellow` | `#f9f002` | 标志黄强调色 |
| `--cyber-red` | `#ff013c` | 警告红 |
| `--cyber-bg` | `#000000` | 纯黑底色 |
| `--cyber-cyan-rgb` | `0, 230, 246` | Tailwind rgba 机制用 |
| `--z-sidebar` | `100` | 侧边栏主体 z-index |
| `--z-sidebar-trigger` | `110` | 侧边栏触发轴 z-index |
| `--z-overlay` | `9999` | CRT 扫描线覆盖层 |

---

## 全局视觉效果

| 效果 | 实现 |
|------|------|
| 准星光标 | `body { cursor: crosshair !important }` 全局覆盖 |
| 标题色差毛刺 | `h1,h2 { text-shadow: 3px 3px var(--cyber-red), -2px -2px var(--cyber-cyan) }` |
| CRT 扫描线 | `body::before` 伪元素：点矩阵 + 扫描线渐变，z-9999，`pointer-events:none` |
| 赛博滚动条 | `::-webkit-scrollbar` 霓虹青配色，0px 圆角直角工业风 |

---

## 输入框分类

| 类名 | 样式 | 使用位置 |
|------|------|----------|
| 默认 `input[type=text/email/number]` | 黄色聚焦光晕动画 | 登录页 |
| `input[type=password]` | Hacked 字体 + 黄色光晕 | 密码框 |
| `.cyan-input` | 透明底 + 青边框，聚焦无动画 | MediaToolbar 搜索 |
| `.neural-input/textarea/select` | 透明底 + 青色，neural 界面专用 | SettingsHub |

---

## 关键动画

| 动画名 | 效果 | 使用位置 |
|--------|------|----------|
| `scanline-move` | CRT 扫描线纵向滚动 | body::before |
| `hologram-float` | 上下浮动 10px（3s 周期）| 统计卡片 |
| `fade-in` | opacity 0→1 + translateY 10px→0 | 视图切换 |
| `input-glow-pulse` | 黄色光晕脉冲（2.5s）| 聚焦输入框 |
| `buttonhover` | X 轴 skew 故障动画 | cyberpunk 按钮 hover |
| `login-scan` | 进度条扫光从左到右 | 登录进度条 |
| `glitch-x` | X 轴 ±3px 偏移故障 | 登录提交按钮 |
