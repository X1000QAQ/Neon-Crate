# NFO 深度纠偏弹窗重构侦察报告

**文档编号**：DEV-RECON-016  
**日期**：2026-03-15  
**状态**：✅ 侦察完成，修改方案已规划

---

## 一、现状全景

### 1.1 `RebuildDialog.tsx` 结构分析

```
RebuildDialog
├── Header（模式标签 + 关闭按钮）
├── Task info strip（文件名 ID）
├── Body（滚动区）
│   ├── [非NFO] 简单说明文字
│   └── [NFO模式]
│       ├── 媒体类型选择器（movie/tv）
│       ├── TMDB 搜索栏
│       ├── 搜索结果列表
│       ├── 已选中摘要
│       └── ☢️ 核级重置开关（复选框样式）
└── Footer
    ├── 取消按钮
    └── 确认执行按钮（动态样式）
            ├── 未选中 → 灰色禁用
            ├── 已选中 + 非核级 → 青色（普通确认）
            └── 已选中 + 核级 → 红色（核级）
```

### 1.2 问题定位

**问题1**：普通确认路径（选片 + 不勾核级）只传 `tmdb_id` 给后端 `manual_rebuild`，后端会更新元数据但不清理目录，目录混乱根本未解决。

**问题2**：核级重置是一个**可选的复选框**，容易被用户忽略，导致执行了「无效确认」。

**问题3**：Footer 确认按钮文案是「确认执行」，不区分普通/核级模式，语义不明。

---

## 二、调用链分析

```
前端 RebuildDialog
  └─ onConfirm({ tmdb_id, media_type, nuclear_reset })
       ↓
  MediaTable.handleRebuildConfirm()
       ↓
  api.manualRebuild(taskId, isArchive, { tmdb_id, media_type, nuclear_reset, ... })
       ↓
  POST /tasks/manual_rebuild
       ↓
  scrape_task.manual_rebuild()
    ├─ nuclear_reset=false → 仅更新 NFO/海报/字幕，目录不变
    └─ nuclear_reset=true  → _nuclear_clean_directory() + 重命名 + 重刮削
```

**结论**：后端 `_nuclear_clean_directory` 是深度纠偏的唯一有效路径，前端需强制 `nuclear_reset=true`。

---

## 三、修改方案（待点火）

### Phase 1 — RebuildDialog.tsx UI 重构

**NFO 模式下的改动**：

1. **删除核级重置复选框**（`nuclearReset` state 及其 toggle UI）
2. **删除普通「确认执行」按钮**
3. **新增唯一 Action 按钮**：「☢️ 执行核级重构 (Nuclear Rebuild)」
   - 始终 `nuclear_reset=true`
   - 需先选中 TMDB 结果才可点击（`disabled={!selected}`）
   - 红色危险样式：`bg-red-500 text-white border-red-400`
   - 点击后触发二次确认（`NeuralConfirmModal`）
4. **更新说明文字**：明确告知「此操作将清理目录杂质并重新从云端检索元数据」

### Phase 2 — 弹窗逻辑路径收拢

- `handleConfirm` 函数始终传 `nuclear_reset: true`
- 移除 `nuclearReset` state（useState 删除）
- 移除 `canConfirm` 的 `nuclearReset` 分支判断

### Phase 3 — 非 NFO 模式保持不变

- `poster` / `subtitle` 模式不涉及核级重置，逻辑不变

---

## 四、流程示意图（重构后）

```
用户点击「NFO 深度纠偏」
  ↓
RebuildDialog 打开（NFO 模式）
  ↓
[搜索 TMDB] → 选中正确片目
  ↓
唯一按钮：「☢️ 执行核级重构 (Nuclear Rebuild)」
  ↓（disabled 直到选中片目）
点击 → NeuralConfirmModal 二次确认弹出
  ↓ 确认
onConfirm({ tmdb_id, media_type, nuclear_reset: true })
  ↓
MediaTable.handleRebuildConfirm()
  ↓
POST /tasks/manual_rebuild
  { tmdb_id, media_type, nuclear_reset: true }
  ↓
_nuclear_clean_directory()  ← 唯一深度纠偏路径
  ├─ 清除非视频文件（NFO/poster/字幕残留）
  ├─ 重命名视频文件为新片名
  └─ 同步 DB target_path
  ↓
重新触发刮削（refix_nfo + refix_poster + refix_subtitle = True）
  ↓
前端收到成功响应 → 刷新列表
```

---

## 五、风险评估

| 风险点 | 等级 | 说明 |
|--------|------|------|
| 误删 `_nuclear_clean_directory` | ZERO | 此函数不在前端，后端不修改 |
| poster/subtitle 模式受影响 | ZERO | 仅修改 NFO 分支 UI |
| 二次确认 Modal 层级 | LOW | 需确保 z-index > RebuildDialog (9999) |
| `canConfirm` 逻辑简化 | LOW | 只需 `!!selected` 即可 |

*Neon Crate | DEV-RECON-016 | 2026-03-15*
