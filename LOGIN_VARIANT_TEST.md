# Login Variant Test - 登录模块变体测试

## 位置
沙盒页面 (`/sandbox`) - 登录界面下方

## 4 种赛博朋克风格变体

### 方案 A：重型液压 (Heavy Hydraulic)
**特点：**
- 强化边框感：16px 黄色实心边框，左侧和顶部加厚
- 底部黄色斜纹装饰 (yellow-stripes)
- 左上角 40px 斜角裁剪
- 输入框：4px 黄色边框
- 按钮：黄色实心 + 斜纹背景 + 实体投影

**技术实现：**
- `border: 16px solid var(--yellow-color)`
- `clip-path: polygon(40px 0, 0 40px, ...)`
- `backgroundImage: repeating-linear-gradient(135deg, ...)`

---

### 方案 B：全息投影 (Holographic Link)
**特点：**
- 去掉实心背景：`background: transparent`
- 极细青色发光线：1px 边框 + 外发光
- 输入框：底线高光模式（仅 border-bottom）
- 按钮：青色线框 + 悬停填充效果
- 毛玻璃效果：`backdrop-filter: blur(8px)`

**技术实现：**
- `border: 1px solid var(--cyber-cyan)`
- `box-shadow: 0 0 25px rgba(0, 230, 246, 0.4), inset 0 0 25px rgba(0, 230, 246, 0.08)`
- 输入框：`border-b-2 border-[var(--cyber-cyan)]`

---

### 方案 C：军用加密 (Mil-Spec Encrypted)
**特点：**
- 整体色调：警告红 (`var(--cyber-red)`)
- 标题：强烈 Glitch 抖动效果 (`glitch-text` 动画)
- 密码输入框：Hacked 字体 + 红色微光
- 输入时：红色呼吸光晕动画 (`red-glow-pulse`)
- 按钮：红色实心 + 悬停抖动

**技术实现：**
- `border: 6px solid var(--cyber-red)`
- `animation: glitch-text 1.2s infinite`
- `fontFamily: 'Hacked, monospace'`
- `textShadow: '0 0 8px rgba(255, 1, 60, 0.6)'`

---

### 方案 D：极简黑客 (Minimalist Terminal)
**特点：**
- 模仿 Linux 终端登录
- 无方框：纯黑背景，无边框
- 青色文字提示符：`root@neon-crate:~$ login`
- 输入框：隐藏边框，仅保留闪烁光标
- 按钮：终端命令风格 `$ ./authenticate.sh _`

**技术实现：**
- `background: #000000; border: none`
- `fontFamily: 'Hacked, monospace'`
- `caret-color: var(--cyber-cyan)`
- `animation: caret-blink 1s step-end infinite`

---

## 按钮风格对比

| 方案 | 按钮样式 | 颜色 | 特效 |
|------|---------|------|------|
| A | 黄色实心 + 斜纹 | `var(--cyber-yellow)` | 实体投影 + 斜纹背景 |
| B | 青色发光线框 | `var(--cyber-cyan)` | 外发光 + 悬停填充 |
| C | 红色实心 + 警告 | `var(--cyber-red)` | 红色光晕 + 悬停抖动 |
| D | 终端命令文本 | `var(--cyber-cyan)` | 文字悬停变色 |

---

## 查看方式
1. 启动开发服务器：`cd frontend && npm run dev`
2. 访问：`http://localhost:3000/sandbox`
3. 向下滚动到 "LOGIN VARIANT TEST" 区域
4. 4 个变体以 2x2 网格平铺展示

---

## 技术栈
- **框架：** Next.js 14 + React + TypeScript
- **样式：** Tailwind CSS + CSS-in-JS (styled-jsx)
- **字体：** Advent Pro (科技感) + Hacked (黑客字体)
- **动画：** CSS Keyframes (Glitch、呼吸光晕、光标闪烁)
- **设计参考：** cyberpunk-2077.css + Neon-Crate 视觉指导文档
