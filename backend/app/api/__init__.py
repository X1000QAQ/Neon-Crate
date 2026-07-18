"""
API 路由层包入口。

职责：
- 承载鉴权路由、v1 版本化 API 和各业务端点。
- 实际路由装配由 `app.core.app_factory` 和 `app.api.v1.api` 完成。
"""
