# CyberParticles — Canvas 粒子背景

**文件路径**: `frontend/components/common/CyberParticles.tsx`  
**组件类型**: `'use client'`  
**层级**: `fixed inset-0 z-0 pointer-events-none`

---

## 职责

使用 Canvas 2D API 渲染全屏赛博朋克粒子动画，作为所有页面的视觉底层。

---

## 动画元素

### ASCII 字符雨

```
字符集: '0123456789ABCDEF'（美式黑客风格）
字体大小: 12px monospace
列数: (width / fontSize) × 2.2（高密度）
颜色: --yellow-color-opacity (#f9f00242)
每列速度: 0.4 ~ 1.8（随机，制造失真感）
```

### 明黄方块粒子

```
数量: 60 个
大小: 2 ~ 6px 随机方块
速度: (1~4) × 0.4（降速至 40%，更沉稳）
透明度: 0.1 ~ 0.4（低饱和度，深邃感）
拖影: 青色 rgba(0, 230, 246, 0.3) 短条
```

---

## 性能优化

| 措施 | 说明 |
|------|------|
| `clearRect` 每帧全量清空 | 保持底层壁纸可见，不使用半透明叠加 |
| `requestAnimationFrame` | 与屏幕刷新率同步，不固定帧率 |
| `willChange: transform` | 提示浏览器独立合成层，减少重绘 |
| `pointer-events: none` | 不拦截任何鼠标/触摸事件 |
| resize 监听 + 清理 | 窗口大小变化时重置 canvas 尺寸 |

---

## 颜色来源

```typescript
const styles = getComputedStyle(document.documentElement);
const yellowOpacity = styles.getPropertyValue('--yellow-color-opacity').trim();
// 值: '#f9f00242'
```

从 CSS 变量读取，与全局主题保持一致。
