# AliExpress 验证码通用 Solver 主线接入设计

日期：2026-05-13

## 目标

把 `.claude/worktrees/captcha-slider-solver` 中已经验证过的一版滑块验证码自动尝试逻辑接入当前主线代码，并统一成一个可复用的 captcha solver 入口。

目标行为：

- 任意主链路页面一旦识别为 captcha
- 先自动尝试一次滑块求解
- 求解成功则继续原业务流程
- 求解失败则回退到现有 `captcha_blocked` / 冷却 / 中断逻辑

第一版只要求主线的两个真实触点完成接入：

- `session preflight`
- 商品详情页 enrichment

但结构上要做成通用入口，后续新的 captcha 触点不再复制求解细节。

## 现状证据

当前主线已经具备 captcha 识别和阻断链路：

- `ali_mvp/browser.py`
  - `_is_captcha_page(...)`
  - `_wait_for_captcha_resolution(...)`
- `ali_mvp/session_guard.py`
  - `run_session_preflight(...)`
  - captcha 直接分类为 `captcha_blocked`
- `ali_mvp/scrape_runner.py`
  - 已消费 `captcha_blocked`
  - 已实现 session cooldown / resume / blocked 状态传播

当前主线行为是：

- 识别出 captcha 后不自动求解
- 详情页会等待一段时间看验证码是否人工消失
- preflight 会直接阻断并进入既有冷却逻辑

`captcha-slider-solver` worktree 中已存在一版自动求解实现，主要内容包括：

- `try_solve_captcha(page, timeout_seconds=30.0)`
- `_is_slider_captcha(page)`
- `_get_slider_distance(page)`
- `_generate_slider_trajectory(distance)`
- `_solve_slider_captcha(page, timeout_seconds=30.0)`

以及两处接入痕迹：

- `browser.py` 中在 `_wait_for_captcha_resolution(...)` 内调用自动滑块尝试
- `session_guard.py` 中在 preflight 命中 captcha 时先尝试自动求解

这说明当前目标不是从零设计 solver，而是把一版已存在的实验实现整理为主线可维护结构。

## 设计原则

### 1. 统一入口，局部接入

本次不把滑块逻辑散落进各个业务函数。

统一入口负责：

- 检测是否可自动求解
- 对支持的 captcha 类型执行一次求解
- 向调用方返回明确布尔结果

当前只改动两个调用点：

- preflight
- detail

未来其他页面如果出现 captcha，也应调用同一入口。

### 2. 失败时不改变现有业务语义

求解失败不引入新的阻断状态，不改 CSV 主结果字段语义，不改 cooldown 策略。

仍然沿用现有：

- `captcha_blocked`
- `detail_skipped_after_captcha`
- `last_block_reason="captcha_blocked"`
- preflight captcha 冷却时间策略

这样可以保证接入 solver 是“增强”，不是“重写 captcha 状态机”。

### 3. 默认只自动尝试一次

第一版不做多次重试，不做指数退避，不做更复杂的人类轨迹调度。

原因：

- 用户已明确希望“遇到验证码自动尝试一次，失败后回退”
- 复杂重试会放大风控和不确定性
- 当前应先验证一次自动拖拽是否能稳定提升通过率

### 4. 不把临时实验实现原样硬拷贝进主线

`captcha-slider-solver` worktree 中的核心思路可复用，但需要整理后再进主线：

- 提取到独立模块
- 减少 `browser.py` 继续膨胀
- 保留单测和回归测试
- 清理只适用于实验分支的局部耦合

## 方案对比

### 方案 A：继续把 solver 细节塞进 `browser.py`

做法：

- 直接把滑块识别、轨迹生成、拖拽求解函数追加到 `browser.py`
- 在 `_wait_for_captcha_resolution(...)` 和 `session_guard.py` 中调用

优点：

- 迁移快
- 改动少

缺点：

- `browser.py` 已经偏大，继续堆 captcha 细节会加重维护负担
- 后续支持别的 captcha 类型时会更乱
- 业务页面能力与验证码求解能力边界不清

### 方案 B：抽轻量通用模块（推荐）

做法：

- 新增 `ali_mvp/captcha_solver.py`
- 把 captcha 类型检测、滑块距离计算、轨迹生成、自动拖拽放入模块
- `browser.py` 和 `session_guard.py` 只调用统一入口

优点：

- 结构清晰
- 当前需求足够轻量，不会过度设计
- 后续支持更多 captcha 形式时有稳定扩展点

缺点：

- 比直接塞进 `browser.py` 多一层整理工作

### 方案 C：做完整 registry / strategy 框架

做法：

- 建 solver registry
- 每种 captcha 一个 provider / strategy
- 统一调度和优先级

优点：

- 扩展性最好

缺点：

- 当前只有 slider，过重
- 会稀释这次主线接入的目标

## 最终方案

采用方案 B：

- 新增轻量通用模块 `ali_mvp/captcha_solver.py`
- 当前只支持 slider captcha
- 主线只接入 `preflight + detail`
- 所有失败路径回退到当前阻断语义

## 架构设计

### 新模块边界

新增模块：

- `ali_mvp/captcha_solver.py`

职责：

- 判断当前页面是否是支持自动求解的 captcha
- 执行一次自动求解
- 返回统一结果

不负责：

- session cooldown
- scrape resume 状态机
- 商品详情业务
- 页面导航

建议导出接口：

- `is_slider_captcha(page) -> bool`
- `try_solve_captcha(page, timeout_seconds: float = 30.0) -> bool`

如后续需要，也可以再补：

- `detect_captcha_type(page) -> str`

但第一版不必为了抽象而抽象。

### 主链路调用点

#### 1. `session_guard.run_session_preflight(...)`

现状：

- 初次 `collect_session_signals(...)`
- 一旦分类为 `captcha_blocked` 就直接返回

改造后：

1. 初次收集 session 信号
2. 如果分类为 `captcha_blocked`
3. 调用 `try_solve_captcha(page, timeout_seconds=30.0)`
4. 若成功：
   - 重新采集 session 信号
   - 重新分类
   - 再决定是 `ready/search_not_ready/login_required/...`
5. 若失败：
   - 原样返回 `captcha_blocked`

也就是：

- solver 只作为 captcha 分支上的一次增强尝试
- preflight 原有分类逻辑和 cooldown 消费逻辑不动

#### 2. `browser._wait_for_captcha_resolution(...)`

现状：

- 循环等待，直到页面不再是 captcha
- 不主动求解

改造后：

1. 进入等待函数
2. 如果仍是 captcha，且未尝试过自动求解
3. 检测是否是 slider captcha
4. 是则调用 `try_solve_captcha(...)`
5. 成功则立刻返回 `True`
6. 失败则继续走剩余等待逻辑
7. 超时后仍 captcha，则返回 `False`

这样 detail enrichment 的现有行为保持：

- 自动求解成功：详情采集继续
- 自动求解失败：最终仍 `captcha_blocked`

### 状态与结果

本次不改业务主状态枚举。

保留：

- `captcha_blocked`
- `detail_skipped_after_captcha`
- preflight captcha cooldown 逻辑

不新增 CSV 主字段，不要求修改现有产物格式。

如果需要调试信息，优先采用：

- 控制台输出
- 内部 helper 日志

而不是先扩主结果 schema。

## 实现约束

### 1. 只尝试一次

一个 captcha 页面最多自动尝试一次 solver。

避免：

- 无限循环拖拽
- 高风险高频交互
- 把“等待人工解除”变成“程序暴力重试”

### 2. Slider-only

第一版只支持当前已观察到的 AliExpress slider captcha。

不做：

- 图像点选
- 多阶段拼图
- 短信/手机验证
- 登录态强校验绕过

对于非 slider 的 captcha 或其他验证页面：

- 直接返回求解失败
- 由上层回退到既有 blocked 逻辑

### 3. 尽量复用现有实验分支实现思路

可复用内容：

- slider DOM 特征检测
- 拖动距离估算
- 轨迹生成
- DrissionPage `Actions` 拖拽

需要整理的点：

- 与 `browser.py` 的耦合边界
- import 位置
- 常量命名与组织
- 错误处理和测试组织

## 测试设计

### 1. solver 单测

新增 `tests/test_captcha_solver.py`，覆盖：

- slider captcha 检测为真
- 非 slider 页面检测为假
- 距离获取异常时返回失败
- 轨迹生成基本约束
- 自动求解成功 / 失败返回值

### 2. detail 链路回归

扩展 `tests/test_browser.py`：

- captcha 页面 -> 自动求解成功 -> detail 继续
- captcha 页面 -> 自动求解失败 -> `captcha_blocked`
- 后续商品仍按现有逻辑标记 `detail_skipped_after_captcha`

### 3. preflight 链路回归

扩展 `tests/test_session_guard.py`：

- `captcha_blocked` -> 自动求解成功 -> 重新收集信号并恢复后续分类
- `captcha_blocked` -> 自动求解失败 -> 保持原结果

### 4. 全链路回归

至少跑：

- `python -m pytest tests/test_captcha_solver.py tests/test_session_guard.py tests/test_browser.py -q`

以及全量：

- `python -m pytest -q`

### 5. 实站验证

使用项目 profile：

- `E:\AliExpress\.browser-profile`

验证方式：

- 人工或真实站点触发 slider captcha
- 确认程序会自动尝试一次拖拽
- 成功时不中断主链路
- 失败时仍进入现有 blocked 行为

## 风险与边界

### 1. DOM 结构脆弱

slider captcha 的 DOM id / class 可能变化。

因此实现必须：

- 容忍选择器失败
- 容忍距离计算失败
- 失败时快速返回，不拖垮主链路

### 2. 自动拖拽不保证长期有效

这次接入目标是“提升通过率”，不是“永久绕过风控”。

如果未来失效：

- 只需调整 solver 模块
- 不应波及 scrape/session/detail 的业务状态机

### 3. 不改变高层风控策略

这次不改：

- proxy cooldown 策略
- account/session 策略
- block 计数策略
- resume 策略

solver 只是 captcha 阶段的一个增强能力。

## 非目标

这次明确不做：

- 通用验证码平台接入
- 图像识别或第三方打码
- 多种 captcha 类型自动适配框架
- 浏览器层全面 anti-detect 重构
- 改写 scrape runner 的 cooldown/风控状态机

## 交付结果

本次实现完成后，主线应具备：

- 通用 captcha solver 调用入口
- slider captcha 自动尝试一次
- preflight 自动求解接入
- detail 自动求解接入
- 失败后完全回退现有阻断逻辑
- 对应自动化测试与实站验证
