# 前端修复方案 (AUDIT_FIXES_FRONTEND.md)

## 漏洞 1.1 - RebuildDialog 按钮永久僵死

### 修复前代码
```typescript
const handleNuclearExecute = () => {
  if (executing) return;
  setExecuting(true);
  onConfirm({
    tmdb_id: selected?.tmdb_id,
    media_type: mediaType,
    nuclear_reset: true,
    season: mediaType === 'tv' && season !== '' ? Number(season) : undefined,
    episode: mediaType === 'tv' && episode !== '' ? Number(episode) : undefined,
  });
  onClose();
};
```

### 修复后代码
```typescript
const handleNuclearExecute = async () => {
  if (executing) return;
  setExecuting(true);
  try {
    // onConfirm 是异步操作，需要 await
    await Promise.resolve(onConfirm({
      tmdb_id: selected?.tmdb_id,
      media_type: mediaType,
      nuclear_reset: true,
      season: mediaType === 'tv' && season !== '' ? Number(season) : undefined,
      episode: mediaType === 'tv' && episode !== '' ? Number(episode) : undefined,
    }));
    onClose();
  } catch (err) {
    console.error('[REBUILD] 核级重构失败:', err);
    // 可选：显示错误提示给用户
    // toast.error(`核级重构失败: ${(err as Error).message}`);
  } finally {
    setExecuting(false);  // ✅ 无论成功失败都恢复状态
  }
};
```

### 关键改动
1. 改为 `async` 函数
2. 使用 `try-catch-finally` 包装
3. `finally` 块中恢复 `executing` 状态
4. 添加错误日志

---

## 漏洞 1.2 - MediaTable 静默失败

### 修复前代码
```typescript
const handleRebuildConfirm = useCallback(async (params: ...) => {
  if (!dialogTask) return;
  setRebuildingId(dialogTask.id);
  try {
    await onRebuild({
      task_id: dialogTask.id,
      is_archive: (dialogTask.status || '').toLowerCase() === 'archived',
      media_type: params.media_type,
      refix_nfo: dialogMode === 'nfo',
      refix_poster: dialogMode === 'poster',
      refix_subtitle: dialogMode === 'subtitle',
      tmdb_id: params.tmdb_id,
      nuclear_reset: params.nuclear_reset,
      season: params.season,
      episode: params.episode,
    });
  } finally {
    setRebuildingId(null);  // ❌ 异常被吞掉
  }
}, [dialogTask, dialogMode, onRebuild]);
```

### 修复后代码
```typescript
const handleRebuildConfirm = useCallback(async (params: ...) => {
  if (!dialogTask) return;
  setRebuildingId(dialogTask.id);
  try {
    await onRebuild({
      task_id: dialogTask.id,
      is_archive: (dialogTask.status || '').toLowerCase() === 'archived',
      media_type: params.media_type,
      refix_nfo: dialogMode === 'nfo',
      refix_poster: dialogMode === 'poster',
      refix_subtitle: dialogMode === 'subtitle',
      tmdb_id: params.tmdb_id,
      nuclear_reset: params.nuclear_reset,
      season: params.season,
      episode: params.episode,
    });
    // ✅ 显示成功提示
    console.log('[REBUILD] 补录成功');
    // 如果有 toast 库，可以显示：
    // toast.success('补录成功');
  } catch (err) {
    // ✅ 捕获异常并显示错误
    const errorMsg = (err as Error).message || '补录失败';
    console.error('[REBUILD] 补录失败:', err);
    // 如果有 toast 库，可以显示：
    // toast.error(`补录失败: ${errorMsg}`);
  } finally {
    setRebuildingId(null);  // ✅ 无论成功失败都清空状态
  }
}, [dialogTask, dialogMode, onRebuild]);
```

### 关键改动
1. 添加 `catch` 块捕获异常
2. 在 `catch` 块中记录错误日志
3. 可选：集成 toast 库显示用户提示
4. `finally` 块确保状态被清空

---

## 完整修复文件

### RebuildDialog.tsx 完整修复

在 `handleNuclearExecute` 函数处修改：

```typescript
// 原位置：217-229 行
const handleNuclearExecute = async () => {
  if (executing) return;
  setExecuting(true);
  try {
    await Promise.resolve(onConfirm({
      tmdb_id: selected?.tmdb_id,
      media_type: mediaType,
      nuclear_reset: true,
      season: mediaType === 'tv' && season !== '' ? Number(season) : undefined,
      episode: mediaType === 'tv' && episode !== '' ? Number(episode) : undefined,
    }));
    onClose();
  } catch (err) {
    console.error('[REBUILD] 核级重构失败:', err);
  } finally {
    setExecuting(false);
  }
};
```

### MediaTable.tsx 完整修复

在 `handleRebuildConfirm` 函数处修改：

```typescript
// 原位置：395-408 行
const handleRebuildConfirm = useCallback(async (params: { 
  tmdb_id?: number; 
  media_type: string; 
  nuclear_reset: boolean; 
  season?: number; 
  episode?: number 
}) => {
  if (!dialogTask) return;
  setRebuildingId(dialogTask.id);
  try {
    await onRebuild({
      task_id: dialogTask.id,
      is_archive: (dialogTask.status || '').toLowerCase() === 'archived',
      media_type: params.media_type,
      refix_nfo: dialogMode === 'nfo',
      refix_poster: dialogMode === 'poster',
      refix_subtitle: dialogMode === 'subtitle',
      tmdb_id: params.tmdb_id,
      nuclear_reset: params.nuclear_reset,
      season: params.season,
      episode: params.episode,
    });
    console.log('[REBUILD] 补录成功');
  } catch (err) {
    console.error('[REBUILD] 补录失败:', err);
  } finally {
    setRebuildingId(null);
  }
}, [dialogTask, dialogMode, onRebuild]);
```

---

## 测试用例

### 测试 1.1 - RebuildDialog 异常恢复

**场景**：网络断开时点击「☢️ 执行核级重构」

**预期**：
- 按钮显示「执行中...」
- 网络错误发生
- 按钮恢复为「☢️ 执行核级重构」
- 用户可以再次点击

**验证**：
```bash
# 在浏览器开发者工具中
# 1. 打开 Network 标签
# 2. 勾选「Offline」模拟离线
# 3. 点击「☢️ 执行核级重构」
# 4. 观察按钮状态变化
# 5. 取消「Offline」
# 6. 按钮应该恢复正常
```

### 测试 1.2 - MediaTable 错误提示

**场景**：补录时后端返回 500 错误

**预期**：
- 按钮显示「执行中」
- 后端返回 500 错误
- 控制台显示错误日志
- 按钮恢复正常
- 用户可以再次点击

**验证**：
```bash
# 在浏览器开发者工具中
# 1. 打开 Console 标签
# 2. 点击补录按钮
# 3. 观察控制台是否显示 "[REBUILD] 补录失败:" 日志
# 4. 按钮应该恢复正常
```

---

## 部署检查清单

- [ ] 修改 `RebuildDialog.tsx` 的 `handleNuclearExecute` 函数
- [ ] 修改 `MediaTable.tsx` 的 `handleRebuildConfirm` 函数
- [ ] 运行 `npm run build` 确保编译通过
- [ ] 在开发环境测试异常恢复
- [ ] 在生产环境验证功能正常
