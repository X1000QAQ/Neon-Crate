# Dashboard 装甲重构 - 快速启动指南

## 🚀 如何查看重构效果

### 1. 启动开发服务器

```bash
cd d:\SoftWare\test\Neon-Crate\frontend
npm run dev
```

### 2. 访问 Dashboard

打开浏览器访问：`http://localhost:3000`

---

## 🎯 重构内容概览

### 修改的文件

1. **`frontend/app/globals.css`**
   - 新增 `.cyber-armor-block`（标准装甲块，8px 边框）
   - 新增 `.cyber-armor-block-small`（小型装甲块，6px 边框）
   - 新增 `.cyber-armor-block-mega`（巨型装甲块，10px 边框）

2. **`frontend/components/media/StatsOverview.tsx`**
   - 统计卡片：4 个独立小型装甲块（`.cyber-armor-block-small`）
   - 指令中枢：巨型装甲块（`.cyber-armor-block-mega`）+ 横向三列布局

3. **`frontend/components/media/MiniLog.tsx`**
   - 应用标准装甲块（`.cyber-armor-block`）
   - 移除嵌套色块，使用青色边框分隔日志区

---

## 🛡️ 核心设计原则

### 视觉红线（已严格遵守）

1. **取消嵌套色块**
   - ❌ 禁止：黄底套黄边
   - ✅ 正确：黄框 + 黑芯

2. **重塑几何形状**
   - 顶部中央凸起（页签感）
   - 底部两侧内凹（斜切）
   - 使用 `clip-path: polygon(...)` 精确控制

3. **色彩纯净化**
   - 边框：`var(--yellow-color)` (#f9f002)
   - 背景：`var(--black-color)` (#000000)
   - 点缀：`var(--cyber-cyan)` (#00e6f6)

---

## 📐 装甲块使用指南

### 小型装甲块（统计卡片）

```tsx
<div className="cyber-armor-block-small">
  {/* 标题 - Advent Pro 字体 */}
  <div className="text-[var(--cyber-cyan)] font-bold text-sm uppercase" 
       style={{ fontFamily: 'Advent Pro, sans-serif' }}>
    电影总数
  </div>
  
  {/* 图标 */}
  <Film size={40} className="text-[var(--cyber-yellow)]" />
  
  {/* 数值 - Hacked 字体 */}
  <div className="text-5xl font-bold text-[var(--cyber-yellow)]" 
       style={{ fontFamily: 'Hacked, monospace', letterSpacing: '3px' }}>
    120
  </div>
</div>
```

**特点**：
- 边框：6px 黄色
- 顶部凸起：25%-75%（50% 宽度）
- 底部凹陷：15px
- 悬停：上浮 3px + 缩放 1.02

---

### 标准装甲块（日志容器）

```tsx
<div className="cyber-armor-block">
  {/* 标题区 */}
  <div className="flex items-center gap-3 mb-4">
    <Terminal size={24} className="text-[var(--cyber-cyan)]" />
    <div>
      <h3 className="text-lg font-bold text-[var(--cyber-yellow)] uppercase" 
          style={{ fontFamily: 'Advent Pro, sans-serif' }}>
        实时日志
      </h3>
      <p className="text-[var(--cyber-cyan)] text-xs">最近 20 条系统日志</p>
    </div>
  </div>
  
  {/* 内容区 */}
  <div className="border-2 border-[var(--cyber-cyan)] bg-black p-3">
    {/* 内容 */}
  </div>
</div>
```

**特点**：
- 边框：8px 黄色
- 顶部凸起：30%-70%（40% 宽度）
- 底部凹陷：20px
- 悬停：上浮 2px

---

### 巨型装甲块（指令中枢）

```tsx
<div className="cyber-armor-block-mega">
  {/* 标题 */}
  <div className="mb-6">
    <h3 className="text-2xl font-bold text-[var(--cyber-yellow)] uppercase tracking-widest" 
        style={{ fontFamily: 'Advent Pro, sans-serif' }}>
      SYSTEM COMMAND
    </h3>
    <p className="text-[var(--cyber-cyan)] text-sm">系统指令中枢</p>
  </div>
  
  {/* 横向三列功能区 */}
  <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
    <div className="space-y-4">
      {/* 功能区内容 */}
    </div>
  </div>
</div>
```

**特点**：
- 边框：10px 黄色
- 顶部凸起：35%-65%（30% 宽度）
- 底部凹陷：25px
- 用途：页面视觉压舱石

---

## 🎨 字体应用规范

### Advent Pro（科技感标题）

```tsx
<h3 style={{ 
  fontFamily: 'Advent Pro, sans-serif',
  fontWeight: 700,
  letterSpacing: '2px',
  textTransform: 'uppercase'
}}>
  SYSTEM COMMAND
</h3>
```

**应用场景**：
- 所有标题（h1-h6）
- 标签文字
- 按钮文字

---

### Hacked（黑客终端数值）

```tsx
<div style={{ 
  fontFamily: 'Hacked, monospace',
  letterSpacing: '3px',
  fontSize: '3rem'
}}>
  {stats?.movies || 0}
</div>
```

**应用场景**：
- 数值显示
- 密码输入框
- 敏感数据（API Key、Token）

---

## 🎯 重构效果检查清单

访问 Dashboard 后，检查以下内容：

### 统计卡片区域
- [ ] 4 个独立小型装甲块（黄框黑芯）
- [ ] 顶部中央有凸起（页签感）
- [ ] 底部两侧有内凹（斜切）
- [ ] 标题使用 Advent Pro 字体（青色）
- [ ] 数值使用 Hacked 字体（明黄色，字符间距 3px）
- [ ] 悬停时上浮 + 光晕增强

### 指令中枢区域
- [ ] 单一巨型装甲块（10px 黄框）
- [ ] 左侧标题 + 右侧横向三列布局
- [ ] 三个功能区：物理扫描、元数据检索、查找字幕
- [ ] 每个功能区包含：图标 + 标题 + 说明 + 执行按钮
- [ ] 按钮统一使用 `.cyberpunk.yellow-stripes` 风格

### 实时日志区域
- [ ] 标准装甲块（8px 黄框黑芯）
- [ ] 标题区使用 Advent Pro 字体
- [ ] 日志区用青色边框分隔（非嵌套色块）

### 整体视觉
- [ ] 无"黄底套黄边"现象
- [ ] 所有容器均为黄框黑芯
- [ ] 色彩纯净（仅黄色边框 + 黑色背景 + 青色点缀）
- [ ] 非对称机械造型（上突下凹）

---

## 🐛 常见问题

### Q1: 装甲块边框显示不完整？
**A**: 检查父容器是否有 `overflow: hidden`，装甲块需要足够空间显示 `clip-path` 裁剪效果。

### Q2: Hacked 字体未生效？
**A**: Hacked 字体已通过 `@font-face` 嵌入 `globals.css`，确保样式文件已加载。

### Q3: 悬停效果不流畅？
**A**: 检查是否有其他 CSS 规则覆盖了 `transition` 属性。

---

## 📝 后续优化建议

1. **响应式优化**
   - 移动端适配装甲块尺寸
   - 调整 `clip-path` 参数以适应小屏幕

2. **动画增强**
   - 装甲块加载时的展开动画
   - 按钮点击时的能量脉冲效果

3. **主题扩展**
   - 支持切换不同颜色主题（红色、蓝色、绿色装甲）
   - 保持"框 + 芯"的核心结构

---

**文档版本**: v1.0  
**最后更新**: 2026-03-10  
**状态**: ✅ 装甲归位，视觉纯净
