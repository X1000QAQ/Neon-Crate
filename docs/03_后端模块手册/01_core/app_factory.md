# app_factory.py — FastAPI 应用工厂

**文件路径**: `backend/app/core/app_factory.py`  
**核心函数**: `create_app(lifespan=None) -> FastAPI`

---

## 职责

将原本散落在 `main.py` 的所有配置操作集中到工厂函数，实现：
- 单点配置：所有中间件、路由、异常处理器在一处注册
- 可测试性：测试代码可调用 `create_app()` 获得独立实例
- 单点故障消除：`main.py` 退化为纯启动脚本

---

## 函数说明

### `create_app(lifespan=None) -> FastAPI`

**按序执行以下步骤**：

| 步骤 | 函数 | 说明 |
|------|------|------|
| 1 | `_register_middleware(app)` | 注册 CORS 中间件 |
| 2 | `_register_routers(app)` | 挂载全部路由 |
| 3 | `_register_exception_handlers(app)` | 全局异常捕获 + SPA 404 回退 |
| 4 | `_add_health_check(app)` | `GET /health` 健康检查 |
| 5 | `_mount_static_resources(app)` | 静态资源 + 前端 SPA |

---

## 路由注册顺序

```python
# 1. 鉴权路由（无 JWT 保护）
app.include_router(auth_router, prefix="/api/v1/auth")

# 2. 图片代理路由（需要 JWT）
app.include_router(public_system_router,
    prefix="/api/v1/public",
    dependencies=[Depends(get_current_user)])

# 3. 业务路由（全局 JWT 保护）
app.include_router(api_router,
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)])
```

**路由前缀汇总**：

| 前缀 | 路由组 | JWT 保护 |
|------|--------|----------|
| `/api/v1/auth` | 鉴权（登录/初始化/验证）| ❌ |
| `/api/v1/public` | 图片代理 | ✅ |
| `/api/v1/tasks` | 任务管理 | ✅ |
| `/api/v1/system` | 系统状态 | ✅ |
| `/api/v1/agent` | AI 对话 | ✅ |
| `/health` | 健康检查 | ❌ |
| `/api/v1/assets` | 静态媒体资源 | ❌（路径挂载）|
| `/` | 前端 SPA | ❌（路径挂载）|

---

## 静态资源挂载策略

```python
# 优先使用 Docker 挂载路径 /storage
if os.path.isdir(settings.DOCKER_STORAGE_PATH):
    assets_dir = settings.DOCKER_STORAGE_PATH
else:
    # 回退到 data/posters/（自动创建）
    assets_dir = Path(__file__).parent / "data" / "posters"

app.mount("/api/v1/assets", StaticFiles(directory=assets_dir))
app.mount("/", StaticFiles(directory="static", html=True))  # 前端 SPA
```

---

## 全局异常处理

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={
        "success": False,
        "message": f"服务器内部错误: {str(exc)}"
    })

@app.exception_handler(404)
async def spa_fallback_handler(request, exc):
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return FileResponse("static/index.html")  # SPA 路由回退
```
