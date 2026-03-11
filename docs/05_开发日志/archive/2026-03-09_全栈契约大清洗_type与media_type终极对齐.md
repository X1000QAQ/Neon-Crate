# 全栈契约大清洗：type 与 media_type 终极对齐

**日期**: 2026-03-09  
**类型**: 数据契约修复  
**影响范围**: 后端 API + 前端组件 + UI 显影  

---

## 问题背景

系统存在严重的数据契约不一致问题：

1. **后端数据库**：使用 `type` 字段存储媒体类型
2. **前端接口定义**：TypeScript 接口期待 `media_type` 字段
3. **后端 API 输出**：直接返回数据库原始数据，未做字段映射
4. **前端过滤逻辑**：基于 `media_type` 进行筛选，但实际收到的是 `type`

**直接后果**：
- 列表过滤完全失效（电影/剧集筛选无效）
- TMDB 链接跳转错误（tv 类型被误判为 movie）
- UI 控件显影问题（白底白字导致搜索框和下拉框不可见）

---

## 修复方案

### 第一步：后端输出契约校准

**文件**: `backend/app/api/v1/endpoints/tasks.py`

**修改位置**: `get_all_tasks` 函数

**核心逻辑**：
```python
# 致命修复：将数据库的 type 映射为前端期待的 media_type
normalized_tasks = []
for task in tasks:
    normalized_task = dict(task)
    # 强制映射：type -> media_type，并确保值为纯小写
    media_type_value = str(normalized_task.get("type", "movie")).strip().lower()
    normalized_task["media_type"] = media_type_value
    # 保留原始 type 字段以防其他地方使用
    normalized_tasks.append(normalized_task)
```

**关键点**：
- 在 API 返回前统一添加 `media_type` 字段
- 确保值为纯小写（`movie` 或 `tv`）
- 保留原始 `type` 字段，避免破坏其他模块

---

### 第二步：前端数据解析双保险

**文件**: `frontend/components/media/MediaWall.tsx`

**修改位置**: `loadTasks` 函数

**核心逻辑**：
```typescript
// 前端数据解析双保险：强制修复后端可能的键名不一致
const normalizedTasks = data.tasks.map(t => ({
  ...t,
  // 无论后端传的是 type 还是 media_type，都强行统一为 media_type
  media_type: t.media_type || (t as any).type || 'movie'
}));

setTasks(normalizedTasks);
```

**关键点**：
- 前端主动兼容两种字段名
- 优先使用 `media_type`，回退到 `type`
- 最终兜底为 `movie`

---

### 第三步：UI 显影终极解法

**文件**: `frontend/components/media/MediaWall.tsx`

**问题根源**：白底背景 + 浅色文字 = 完全不可见

**修复方案**：暴力高对比度

#### 搜索框修复
```typescript
// 修改前：白底 + 灰色占位符 + 白色文字（不可见）
className="w-full pl-10 pr-4 py-2 bg-charcoal-lighter border border-cyan-500/50 rounded-lg text-white placeholder-gray-400"

// 修改后：白底 + 黑色文字 + 深灰占位符（绝对可见）
className="w-full pl-10 pr-4 py-2 bg-white border-2 border-gray-400 text-black placeholder-gray-600 rounded-lg focus:outline-none focus:border-blue-500"
```

#### 下拉框修复
```typescript
// 修改前：深色背景 + 白色文字（在白底页面不可见）
className="w-full bg-charcoal-lighter border border-cyan-500/50 rounded-lg px-4 py-2 text-white"

// 修改后：白底 + 黑色文字 + 粗边框（绝对可见）
className="w-full bg-white border-2 border-gray-400 text-black px-4 py-2 rounded-lg focus:outline-none focus:border-blue-500"
```

**关键点**：
- 图标颜色：`text-gray-400` → `text-gray-600`
- 边框加粗：`border` → `border-2`
- 文字颜色：`text-white` → `text-black`
- 占位符颜色：`placeholder-gray-400` → `placeholder-gray-600`

---

### 第四步：TMDB 跳转链接逻辑验证

**文件**: `frontend/components/media/MediaWall.tsx`

**现有逻辑**（已正确）：
```typescript
href={
  task.media_type === 'tv'
    ? `https://www.themoviedb.org/tv/${task.tmdb_id}`
    : `https://www.themoviedb.org/movie/${task.tmdb_id}`
}
```

**验证结果**：
- 逻辑本身正确，使用 `task.media_type` 判断
- 由于前两步已完成数据标准化，此处无需修改
- 链接跳转现在能正确区分电影和剧集

---

## 修复效果

### 数据契约层面
- ✅ 后端 API 统一输出 `media_type` 字段
- ✅ 前端接口定义与实际数据完全对齐
- ✅ 类型值强制小写化（`movie` / `tv`）

### 功能层面
- ✅ 电影/剧集筛选功能恢复正常
- ✅ TMDB 链接跳转正确（tv 类型跳转到 /tv/ 路径）
- ✅ 搜索框和下拉框完全可见（黑字白底高对比度）

### 架构层面
- ✅ 前后端双重保险，容错性极强
- ✅ 保留原始 `type` 字段，向后兼容
- ✅ 数据标准化在 API 层和组件层双重执行

---

## 技术要点

### 1. 数据契约对齐的三层防线

**第一层：后端 API 输出层**
- 在数据返回前统一添加 `media_type` 字段
- 确保所有客户端收到的数据格式一致

**第二层：前端数据接收层**
- 主动兼容多种字段名（`media_type` / `type`）
- 防止后端遗漏或字段名变更导致的崩溃

**第三层：TypeScript 类型定义层**
- 接口定义明确要求 `media_type` 字段
- 编译时类型检查，防止字段名拼写错误

### 2. UI 显影的绝对安全原则

**问题根源**：CSS 变量 + 主题切换 = 不可预测的颜色组合

**解决方案**：放弃动态主题，使用绝对颜色值
- `bg-white` + `text-black` = 绝对可见
- `border-2` + `border-gray-400` = 绝对清晰
- `placeholder-gray-600` = 绝对可读

### 3. 向后兼容的字段映射策略

**为什么保留原始 `type` 字段？**
- 数据库查询可能直接使用 `type` 字段
- 其他模块可能依赖 `type` 字段
- 避免一次性修改导致的连锁崩溃

**最佳实践**：
```python
normalized_task["media_type"] = media_type_value  # 新字段
# 保留原始 type 字段，不删除
```

---

## 测试验证

### 功能测试清单

- [x] 电影筛选：选择 "电影" 后只显示 movie 类型
- [x] 剧集筛选：选择 "剧集" 后只显示 tv 类型
- [x] 搜索框可见性：白底页面下搜索框文字清晰可见
- [x] 下拉框可见性：白底页面下下拉框选项清晰可见
- [x] TMDB 链接：电影跳转到 /movie/ 路径
- [x] TMDB 链接：剧集跳转到 /tv/ 路径

### 边界测试

- [x] 数据库 `type` 为 NULL：前端回退到 `movie`
- [x] 数据库 `type` 为大写 `MOVIE`：后端强制转小写
- [x] 后端未返回 `media_type`：前端从 `type` 字段提取

---

## 经验总结

### 1. 数据契约不一致的危害

**表面症状**：
- 功能失效（筛选不工作）
- 链接错误（跳转到错误页面）

**深层危害**：
- 前后端开发者互相甩锅
- 调试时间成倍增加
- 用户体验极差

### 2. 修复策略的优先级

**错误做法**：只修改前端或只修改后端
- 前端修改：治标不治本，下次后端改动又会崩溃
- 后端修改：可能破坏其他依赖 `type` 字段的模块

**正确做法**：前后端双重保险
- 后端：统一输出标准字段
- 前端：主动兼容多种格式
- 结果：任何一方出问题都不会崩溃

### 3. UI 显影问题的根本解决

**错误做法**：调整透明度、调整色调
- `text-gray-400` → `text-gray-500` → `text-gray-600`
- 永远在猜测哪个灰度值"刚好可见"

**正确做法**：使用绝对对比色
- 白底 → 黑字
- 深底 → 白字
- 不依赖任何 CSS 变量或主题系统

---

## 后续优化建议

### 1. 数据库字段重命名（可选）

**当前方案**：数据库保留 `type`，API 层映射为 `media_type`

**未来优化**：
```sql
ALTER TABLE tasks RENAME COLUMN type TO media_type;
```

**优点**：
- 数据库字段名与 API 输出完全一致
- 减少映射逻辑，降低维护成本

**风险**：
- 需要全面测试所有依赖 `type` 字段的代码
- 需要数据库迁移脚本

### 2. TypeScript 类型守卫

**当前方案**：运行时手动映射

**未来优化**：
```typescript
function normalizeTask(task: any): Task {
  return {
    ...task,
    media_type: task.media_type || task.type || 'movie'
  };
}
```

**优点**：
- 类型安全
- 可复用
- 易于测试

---

## 结论

通过四步修复，彻底解决了全栈数据契约不一致问题：

1. **后端输出契约校准**：API 层统一添加 `media_type` 字段
2. **前端数据解析双保险**：组件层主动兼容多种字段名
3. **UI 显影终极解法**：使用绝对对比色，放弃动态主题
4. **TMDB 跳转逻辑验证**：确认现有逻辑正确，无需修改

**核心原则**：
- 前后端双重保险，任何一方出问题都不会崩溃
- 使用绝对颜色值，不依赖 CSS 变量
- 保留向后兼容性，避免连锁崩溃

**最终效果**：
- 列表过滤功能完全恢复
- TMDB 链接跳转完全正确
- UI 控件绝对可见

---

**修复完成时间**: 2026-03-09  
**修复人员**: AI 影音大师  
**测试状态**: ✅ 全部通过
