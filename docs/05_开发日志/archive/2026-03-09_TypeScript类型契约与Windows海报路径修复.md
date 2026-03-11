# TypeScript 类型契约与 Windows 海报路径修复

## 修复日期
2026-03-09

## 问题描述

### 问题 1：TypeScript 类型错误
MediaWall.tsx 中使用 `task.status === 'archived'` 时出现红色波浪线，提示类型错误。

**根本原因**：
- `frontend/lib/api.ts` 中 Task 接口的 status 类型定义不完整
- 缺少 `'archived'` 和 `'ignored'` 状态值
- 导致前端组件无法正确使用这些状态

### 问题 2：Windows 环境海报路径解析失败
在 Windows 测试环境下，海报路径可能无法被正确替换，导致图片加载失败。

**根本原因**：
- 原有 `getPosterUrl` 函数仅处理 Docker 的 `/storage` 路径
- Windows 使用绝对路径（如 `D:\test\media`），与 Docker 路径体系不兼容
- 缺乏跨平台路径适配能力

---

## 修复方案

### 修复 1：补全 Task 接口类型定义

**文件**：`frontend/lib/api.ts`

**修改前**：
```typescript
export interface Task {
  // ...
  status: 'pending' | 'success' | 'failed';
  // ...
}
```

**修改后**：
```typescript
export interface Task {
  // ...
  status: 'pending' | 'success' | 'failed' | 'archived' | 'ignored';
  // ...
}
```

**效果**：
- TypeScript 类型检查通过
- MediaWall.tsx 中的红色波浪线消除
- 前端类型契约与后端数据库状态完全对齐

---

### 修复 2：增强海报路径跨平台兼容性

**文件**：`frontend/components/media/MediaWall.tsx`

**修改前**：
```typescript
const getPosterUrl = (task: Task): string => {
  if (task.status === 'archived' && task.target_path) {
    const dirPath = task.target_path
      .replace(/^[\/\\]storage[\/\\]/, '')
      .split(/[/\\]/)
      .slice(0, -1)
      .join('/');
    return `/api/v1/assets/${dirPath}/poster.jpg`;
  }
  // ...
};
```

**修改后**：
```typescript
const getPosterUrl = (task: Task): string => {
  if (task.status === 'archived' && task.target_path) {
    let dirPath = '';
    
    // 兼容 Docker AIO 模式
    if (task.target_path.startsWith('/storage')) {
      dirPath = task.target_path.replace(/^[\/\\]storage[\/\\]/, '');
    } 
    // 兼容 Windows 开发测试模式 (例如截取 test\media 之后的部分)
    else if (task.target_path.includes('media')) {
      const parts = task.target_path.split(/[/\\]/);
      const mediaIndex = parts.indexOf('media');
      if (mediaIndex !== -1) {
        dirPath = parts.slice(mediaIndex + 1).join('/');
      } else {
        // 兜底：清理盘符
        dirPath = task.target_path.replace(/^[a-zA-Z]:[/\\]/, '');
      }
    } else {
      // 兜底全路径清理
      dirPath = task.target_path.replace(/^[a-zA-Z]:[/\\]/, '');
    }

    dirPath = dirPath.split(/[/\\]/).slice(0, -1).join('/');
    return `/api/v1/assets/${dirPath}/poster.jpg`;
  }
  
  // 兜底方案：TMDB 在线海报
  if (task.poster_path) {
    return `https://image.tmdb.org/t/p/w500${task.poster_path}`;
  }
  return '/placeholder-poster.jpg';
};
```

**智能替换逻辑**：
1. **Docker AIO 模式**：识别 `/storage` 前缀，直接替换
2. **Windows 开发模式**：识别 `media` 目录，提取相对路径
3. **兜底机制**：清理 Windows 盘符（如 `D:\`），确保路径可用

---

## 测试验证

### TypeScript 类型检查
```bash
npx tsc --noEmit
```

**结果**：
- ✅ MediaWall.tsx 无类型错误
- ✅ Task 接口类型契约完整
- ✅ 红色波浪线已消除

### 路径兼容性测试

**Docker 环境**：
```
输入：/storage/Movies/Dune/Dune.mkv
输出：/api/v1/assets/Movies/Dune/poster.jpg
```

**Windows 环境**：
```
输入：D:\test\media\Movies\Dune\Dune.mkv
输出：/api/v1/assets/Movies/Dune/poster.jpg
```

---

## 技术要点

### 1. TypeScript 联合类型补全
确保前端类型定义与后端数据库状态完全一致，避免类型错误。

### 2. 跨平台路径处理
使用正则表达式 `/[/\\]/` 同时匹配 Unix 和 Windows 路径分隔符。

### 3. 多层兜底机制
- 优先匹配 Docker 路径
- 其次匹配 Windows 相对路径
- 最后清理绝对路径前缀

### 4. 遵循 Windows 避坑指南
严格遵循 `docs/03_开发日志/Windows环境避坑指南.md` 中的路径处理规范。

---

## 影响范围

### 修改文件
- `frontend/lib/api.ts`（1 处修改）
- `frontend/components/media/MediaWall.tsx`（1 处修改）

### 影响功能
- ✅ 媒体墙海报显示
- ✅ 归档任务状态识别
- ✅ Windows 开发环境兼容性

---

## 后续建议

1. **统一路径处理**：考虑将路径转换逻辑抽取为独立工具函数
2. **环境变量配置**：允许用户自定义媒体库根目录名称（如 `media`、`storage`）
3. **单元测试**：为路径转换逻辑添加单元测试，覆盖 Docker 和 Windows 场景

---

**修复人员**：首席前端架构师  
**文档版本**：V1.0  
**状态**：✅ 已完成
