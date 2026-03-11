# Windows 环境避坑指南

## 前言

AI Media Master 在 Windows 平台开发过程中遭遇了多个系统级陷阱，本文档记录所有血泪教训及解决方案。

## 陷阱一：编码刺客

### 问题描述

Windows PowerShell 默认使用 GBK 编码，当 Python 脚本输出 Unicode Emoji 或特殊字符时，会触发 `UnicodeEncodeError` 导致程序崩溃。

### 崩溃现场

```python
print("字幕下载成功")  # 正常
print("字幕下载成功 ✅")  # 崩溃！
```

错误信息：
```
UnicodeEncodeError: 'gbk' codec can't encode character '✅' in position 7
```

### 根本原因

- PowerShell 默认编码为 `cp936`（GBK）
- Python 的 `print` 函数会尝试将输出编码为终端编码
- Emoji 字符无法用 GBK 编码，导致崩溃

### 解决方案

#### 方案一：强制 ASCII 输出（推荐）

```python
# 禁止在 print 输出中使用任何 Emoji
print("[OK] 字幕下载成功")  # 使用纯文本标记
```

#### 方案二：设置环境变量

```powershell
$env:PYTHONIOENCODING = "utf-8"
python main.py
```

#### 方案三：修改 PowerShell 编码

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

### 强制规范

**所有 Python 脚本的 print 输出严禁使用 Emoji，必须使用纯 ASCII 字符。**

---

## 陷阱二：幽灵端口

### 问题描述

后端启动时报错 `OSError: [WinError 10048] 通常每个套接字地址(协议/网络地址/端口)只允许使用一次`，但使用 `netstat -ano | findstr 8000` 查询显示端口未被占用。

### 崩溃现场

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# OSError: [WinError 10048] Address already in use
```

### 根本原因

- Python 进程未正常退出，残留后台进程占用端口
- `netstat` 无法显示某些僵尸进程的端口占用
- Windows 端口释放存在延迟（TIME_WAIT 状态）

### 解决方案

#### 方案一：强制杀死 Python 进程（推荐）

```powershell
# 必须以管理员身份运行 PowerShell
Get-Process python | Stop-Process -Force
```

#### 方案二：查找并杀死占用端口的进程

```powershell
# 查找占用 8000 端口的进程 PID
netstat -ano | findstr :8000

# 杀死进程（替换 <PID> 为实际进程 ID）
taskkill /PID <PID> /F
```

#### 方案三：更换端口

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 预防措施

1. 使用 `Ctrl+C` 正常停止服务，避免强制关闭终端
2. 开发时使用 `--reload` 参数，避免手动重启
3. 定期清理僵尸进程

---

## 陷阱三：前端缓存雪崩

### 问题描述

Next.js 频繁修改组件后，前端报错 `Error: Cannot find module` 或页面白屏，重启 `npm run dev` 无效。

### 崩溃现场

```bash
npm run dev
# Error: Cannot find module 'D:\project\.next\server\pages\index.js'
```

### 根本原因

- Next.js 的 `.next` 缓存目录损坏
- 热更新（HMR）机制失效
- 模块依赖关系混乱

### 解决方案

#### 方案一：物理删除缓存目录（推荐）

```powershell
# 停止开发服务器
# Ctrl+C

# 强制删除 .next 目录
Remove-Item -Recurse -Force .next

# 重启开发服务器
npm run dev
```

#### 方案二：清理 node_modules（终极方案）

```powershell
Remove-Item -Recurse -Force node_modules
Remove-Item -Force package-lock.json
npm install
npm run dev
```

### 预防措施

1. 避免在开发服务器运行时修改 `next.config.js`
2. 避免频繁切换 Git 分支
3. 定期清理 `.next` 目录（每周一次）

---

## 陷阱四：路径分隔符地狱

### 问题描述

Windows 使用反斜杠 `\` 作为路径分隔符，而 Python 字符串中 `\` 是转义字符，导致路径解析错误。

### 崩溃现场

```python
path = "D:	est
ew_folder"  # 错误！	 和 
 被解析为转义字符
```

### 解决方案

#### 方案一：使用原始字符串（推荐）

```python
path = r"D:	est
ew_folder"
```

#### 方案二：使用正斜杠

```python
path = "D:/test/new_folder"  # Windows 也支持正斜杠
```

#### 方案三：使用 Path 对象

```python
from pathlib import Path
path = Path("D:/test/new_folder")
```

---

## 陷阱五：权限拒绝

### 问题描述

某些操作（如删除文件、创建硬链接）报错 `PermissionError: [WinError 5] 拒绝访问`。

### 解决方案

1. 以管理员身份运行 PowerShell
2. 检查文件是否被其他进程占用（使用 Process Explorer）
3. 关闭杀毒软件的实时保护
4. 检查文件/目录的 NTFS 权限

---

## 陷阱六：长路径限制

### 问题描述

Windows 默认路径长度限制为 260 字符，超长路径会导致文件操作失败。

### 解决方案

#### 启用长路径支持

1. 打开注册表编辑器（`regedit`）
2. 导航到 `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\FileSystem`
3. 将 `LongPathsEnabled` 设置为 `1`
4. 重启计算机

#### 或使用组策略

1. 运行 `gpedit.msc`
2. 导航到"计算机配置 > 管理模板 > 系统 > 文件系统"
3. 启用"启用 Win32 长路径"

---

## 陷阱七：路径硬编码地狱

### 问题描述

代码中硬编码以 `/` 开头的绝对路径（如 `/app/data`、`/storage`），在 Windows 环境下会导致路径解析失败，引发文件未找到、静态资源挂载失败等问题。

### 崩溃现场

```python
# 错误示例 1：硬编码 Docker 路径
APP_LOG_PATH = Path("/app/data/logs/app.log")  # Windows 下无法访问

# 错误示例 2：硬编码挂载点
if os.path.isdir("/storage"):
    app.mount("/api/v1/assets", StaticFiles(directory="/storage"))
```

### 根本原因

- Docker 容器内路径（如 `/app`、`/storage`）在 Windows 宿主机上不存在
- Windows 使用盘符路径（如 `D:\project`），与 Unix 路径体系不兼容
- 硬编码路径缺乏跨平台适配能力

### 解决方案

#### 方案一：使用相对路径 + Path(__file__)（推荐）

```python
from pathlib import Path

# 正确：基于当前文件计算项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
APP_LOG_PATH = BASE_DIR / "data" / "logs" / "app.log"

# 确保目录存在
APP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
```

#### 方案二：环境变量 + 回退机制

```python
import os
from pathlib import Path

# 优先使用环境变量，Windows 环境自动回退
DOCKER_STORAGE_PATH = os.getenv("STORAGE_PATH", "/storage")

if os.path.isdir(DOCKER_STORAGE_PATH):
    assets_dir = DOCKER_STORAGE_PATH
else:
    # Windows 回退方案
    fallback_dir = Path(__file__).resolve().parent.parent / "data" / "posters"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = str(fallback_dir)
```

### 强制规范

**禁止在代码中硬编码以 `/` 开头的绝对路径，必须使用 `Path(__file__)` 结合相对路径，或提供 Windows 回退机制。**

---

## 最佳实践总结

1. **编码规范**: 所有文件操作强制使用 UTF-8 编码
2. **路径处理**: 统一使用 `pathlib.Path` 处理路径
3. **路径自适应**: 禁止硬编码绝对路径，必须使用相对路径或回退机制
4. **进程管理**: 定期清理僵尸进程
5. **缓存清理**: 定期删除 `.next` 和 `__pycache__` 目录
6. **权限管理**: 开发时以管理员身份运行终端
7. **日志输出**: 禁止使用 Emoji，使用纯 ASCII 字符

---

**文档版本**: V1.1  
**最后更新**: 2026-03-09  
**适用平台**: Windows 10/11
