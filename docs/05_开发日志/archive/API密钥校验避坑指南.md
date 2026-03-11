## API 密钥校验避坑指南

**日期**: 2026-03-09  
**类型**: 鉴权与路由调试实战复盘  
**影响范围**: `/api/v1` 业务路由、`/api/v1/public` 公开路由、前端 `<img>/<video>` 直链访问

---

### 一、403 隐形阻断：FastAPI 路由嵌套导致的“全局鉴权误杀”

#### 1.1 现场回放

现象很诡异：

- 新加了一个**自认为“公开”的接口**，代码里没写任何鉴权逻辑  
- Postman/浏览器一打，直接 **403**，连你写在接口里的 `print` / `logger.info` 都完全不出现  
- 换了好几个 URL / 参数，结果**全部被秒拒**，业务逻辑一行都没执行

第一反应：  
> “肯定是后端校验代码写挂了！”

真实原因其实是：

> **接口被悄悄挂进了带全局依赖的路由组**，被 `Depends(get_current_user)` 在路由层提前拦截了。

#### 1.2 架构复盘：是谁在“全局加料”

根据《API 规范与鉴权架构说明 V1.0》，后端核心挂载逻辑在 `main.py` 中，大致是这样的：

- `auth_router`：登录 / 初始化等鉴权接口，**显式豁免 JWT**
- `public_system_router`：`/api/v1/public/*` 公共接口（图片代理等），**不走 JWT，用路径安全兜底**
- `api_router`：所有业务路由的集合，统一挂载到 `/api/v1`，并且：
  - `dependencies=[Depends(get_current_user)]`
  - 也就是：**只要被 include 到 `api_router` 里的接口，默认都必须带 JWT**

于是坑就来了：

- 你在 `app/api/v1/endpoints/xxx.py` 写了个新路由  
- 在 `app/api/v1/api.py` 里顺手 `include_router(xxx.router, prefix="/xxx", tags=["XXX"])`  
- **从那一刻起，这个新接口就已经自动被全局鉴权保护了**，即使你在 handler 里一句鉴权都没写。

#### 1.3 为什么你看不到任何业务日志？

关键点在于：  
`Depends(get_current_user)` 是挂在 `include_router` 这一层的**全局依赖**。

- 请求进来时，FastAPI 会先跑依赖  
- 如果 Token 校验在依赖阶段就挂了，**请求根本进不到你的 handler**  
- 所以控制台上你只会看到一堆 401/403，**完全没有你写在接口里的日志**

也就是说，这不是“日志丢了”，而是**业务根本没开始**。

#### 1.4 快速自查思路

当你遇到“接口刚写好就 403/401，业务日志一条没有”的情况，第一步不要去翻 handler 代码，而是：

1. 打开 `main.py`，看清楚：
   - 哪些 router 是挂在 `api_router` 下并带 `Depends(get_current_user)` 的
   - 哪些 router 是挂在 `/api/v1/public` 下的
2. 打开 `app/api/v1/api.py`：
   - **确认你的新接口是被挂在哪个 router 下面**
   - 如果它通过 `api_router.include_router(...)` 进来的，那默认就是“必须 JWT”

一句话总结：

> **"我没写鉴权" 不代表 "它没在被鉴权"。路由层的依赖比 handler 更有话语权。**

---

### 二、标签属性限制：为什么 `<img>/<video>` 老是打不过 JWT

#### 2.1 天然短板：标签的 src 带不了自定义 Header

浏览器的 `<img>`、`<video>` 这些标签，用起来很爽，但有个致命限制：

- 你只能填一个 URL 到 `src`  
- **你没办法给它顺手加上 `Authorization: Bearer xxx` 这种自定义 Header**

这在我们现在这套 API 体系里就意味着：

- 所有挂在 `/api/v1`、受 `Depends(get_current_user)` 保护的接口  
- **都不能直接用 `<img src="...">` 或 `<video src="...">` 去访问**

不然结果就只有一个字：**403**。

#### 2.2 正确姿势：要么“豁免”，要么“改协议”

结合当前架构，处理这类需求只有两条路：

- **方案 A：走公开路由（推荐）**
  - 把这类资源接口挂到 `/api/v1/public/...` 下
  - 用类似图片代理那一套：路径清洗 + 黑名单 + 后缀白名单，来兜安全
  - 典型例子：`/api/v1/public/image?path=...`

- **方案 B：走 URL Token 协议**
  - 不再靠 Header 携带身份，而是通过带签名的 URL Token 访问
  - 形如：`/api/v1/some-resource?token=<一次性/短期有效签名>`
  - 这套方案更偏“分享链接/外链直链”方向，目前项目内重点还是走 A 方案

实战建议：

- **凡是前端组件里出现 `<img src="...">` / `<video src="...">` 的地方，优先考虑 `/api/v1/public/*` 路径**
- 绝不要把这类 URL 写成 `/api/v1/tasks/...` 这种业务路由，然后指望 JWT 能神奇带进去

---

### 三、调试探针失效：为什么你看不到任何业务日志

#### 3.1 常见误区

排查 403 时，很多同学会习惯性操作：

- 在 handler 顶部加一行 `logger.info("XXX called")`  
- 甚至在函数第一行打断点、加个 `print("here")`  
- 然后发现：**日志没打出来，断点也一次没停过**

这时候容易怀疑：

- “是不是框架日志配置有问题？”  
- “是不是 uvicorn 没打印我的日志？”  
- “是不是 Next.js/前端没把请求打过来？”

实际上，大多数情况下锅在这里：

> **请求连 handler 都没摸到，就在依赖或中间件层被拦截了。**

#### 3.2 正确的排查顺序

当你看到 403（尤其是统一鉴权体系里）时，推荐按照下面顺序排查：

1. **先看路由挂载顺序（`main.py`）**
   - 当前这个 URL，走的是 `/api/v1` 还是 `/api/v1/public`
   - 是否挂在了带 `Depends(get_current_user)` 的 router 上
2. **再看依赖和中间件**
   - `get_current_user` 里面有没有提前抛 `HTTPException(403/401)`  
   - 有没有统一的鉴权中间件在请求进入路由前就拦截
3. **最后才是 handler 代码本身**
   - 参数校验  
   - 业务逻辑里的 403/404/422 等

重点心法：

> 排查 403 时，**第一反应是查“路由 + 依赖”**，不是去翻你刚写的业务代码。

---

### 四、跨平台路径转义：Windows 的 `\` 怎么变成 404/403 的

#### 4.1 坑怎么来的

在这个项目里，Windows 环境下的典型路径长这样：

- `D:\test\media\Movies\Dune\poster.jpg`

但一旦这玩意儿出现在 URL 或 JSON 里，就开始变得危险了：

- 在 Python 源码里，`\` 是转义字符（`\n`、`\t` 那种）
- 在 URL 里，`\` 又是不标准字符，需要编码
- 前端如果没统一 `encodeURIComponent`，后端如果没统一替换成 `/`，整体就会被玩坏

表现出来就是：

- 同一个图片，Linux/Docker 环境下访问一切正常  
- 换成 Windows 路径之后，要么直接 400/404，要么触发路径安全校验被 403

#### 4.2 现有防御：Path.resolve() + 统一分隔符

在公开图片代理接口里（`/api/v1/public/image`），已经做了一套比较完善的处理：

- 前端：**用 `encodeURIComponent` 把物理路径丢到 `path` 参数里**
- 后端：
  - 先用 `urllib.parse.unquote` 还原
  - 再用 `path.replace("\\", "/")` 把所有 `\` 统一成 `/`
  - 最后用 `Path(clean_path_str).resolve(strict=False)` 做路径归一化 + 防路径穿越

这几步解决的是：

- Windows 的 `\` 不再在 URL 里搞事  
- `..` 之类的路径穿越直接被消解  
- 后续黑名单、白名单统一在 POSIX 风格路径上做判断

实战心法：

- **只要涉及“路径进 URL”，就必须经过“encode → 替换反斜杠 → resolve”这一套**
- 后端看到原始 Windows 路径直接塞进 URL 的，一律先打个问号

---

### 五、实战检查清单（Checklist）

在你新加一个接口，或者调试一个 403/401/404 时，可以对照下面这份清单过一遍。

- [ ] **新接口是否误入了全局鉴权路由组？**  
  - 看 `app/api/v1/api.py`：是不是被 `api_router.include_router(...)` 收进去了？  
  - 如果是，那它默认就要走 `Depends(get_current_user)`，不带 JWT 必挂。

- [ ] **接口是否需要支持浏览器标签直接访问？（`<img>/<video>` 等）**  
  - 如果需要，优先挂到 `/api/v1/public/*`，并参考图片代理实现路径安全逻辑。  
  - 千万别指望 `<img>` 能自动带上 Authorization。

- [ ] **是否已在 `main.py` 中正确调整了路由挂载顺序？**  
  - `auth_router` → `public_router` → 带全局依赖的 `api_router`，顺序要清晰。  
  - 避免把本该公开的接口错误地塞进受保护路由组。

- [ ] **403 排查时，是否先看了“路由 + 依赖”，再看业务代码？**  
  - 如果业务日志一条没有，很可能压根没进 handler。  
  - 优先检查 `get_current_user` 和中间件，而不是埋头在 handler 里找 bug。

- [ ] **跨平台路径是否都做了统一编码和归一化？**  
  - 前端：`encodeURIComponent(path)`  
  - 后端：`unquote` → `"\\" -> "/"` → `Path.resolve()`  
  - 尤其是 Windows 环境，别让 `\` 和盘符把你带沟里去。

---

### 六、收尾：记住这两句话就够了

- **“我没写鉴权” ≠ “接口是公开的”，要看路由挂在哪。**  
- **凡是 `<img>/<video>` 这种带不了 Header 的访问，一律优先考虑 `/api/v1/public/*` 或 URL Token 协议。**

把这两点刻在脑子里，80% 关于 API 密钥 / JWT 的“玄学 403”都能五分钟内搞定。

