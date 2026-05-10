# AliExpress 中文后处理与浏览器最小加固设计

日期：2026-05-11

## 目标

在不破坏当前稳定采集主链路的前提下，新增两类能力：

1. 面向人工审核的中文友好输出
   - 为英文采集结果补充中文翻译
   - 输出适合员工审阅黑名单效果的 HTML 页面
2. 面向稳定性的浏览器最小加固
   - 降低自动化暴露
   - 让滚动、翻页、详情打开节奏不那么机械
   - 保持真实 Chrome profile 驱动，不重写为接口抓取

本设计明确优先级：

- 第一优先级：不影响现有 `scrape` 主链路稳定性
- 第二优先级：让员工更容易审查黑名单是否误判
- 第三优先级：在当前架构内做最小、可回退的抗风控改进

## 现状证据

当前主线已经稳定并合并到 `main`：

- 详情页补全、listing context 恢复、direct detail fallback、captcha 等待都已完成
- `python -m pytest -q` 当前为 `81 passed`

当前输出层只有：

- `products.csv`
- `products_filter_audit.csv`
- `category_rank.csv`

当前输出问题：

- 员工只能看到英文底表，不利于快速审核
- 没有 HTML 审核页，accepted 与 rejected 只能靠 CSV 交叉查看
- 现有 `products_filter_audit.csv` 更偏机器审计，不适合作为人工审核主视图

当前浏览器配置问题：

- `_build_options(...)` 只做了基本端口与 profile 设置
- 滚动、翻页等待节奏较固定
- 没有最小化 automation 暴露的页面初始化步骤

## 设计原则

### 1. 采集与后处理解耦

翻译和 HTML 报表不进入抓取主链路，不在采集过程中调用翻译服务。

原因：

- 翻译服务失败不应拖垮抓取
- 采集与报表是不同职责
- 便于先确认抓取数据，再决定是否需要翻译和报表

### 2. 原始底表不覆盖

英文原始产物继续保留，中文结果以追加字段或新文件的方式输出。

原因：

- 便于追溯与复检
- 避免翻译质量影响原始数据可信度
- 降低对现有下游使用方的破坏

### 3. 浏览器加固只做最小补丁

当前项目基于真实 Chrome + 已登录 profile。加固以一致性和节奏优化为主，不做底层网络栈改造。

明确不做：

- 不做代理池
- 不改 TLS/HTTP2 指纹
- 不改为 `requests` / `httpx` 接口抓取
- 不做重型浏览器指纹伪装

## 方案对比

### 方案 1：后处理翻译 + HTML 审核页 + 浏览器最小加固（推荐）

做法：

- `scrape` 保持现有职责
- 新增 `postprocess` 命令读取已有 run 目录
- 生成中文 CSV、HTML 审核页、翻译缓存
- 浏览器侧做最小 stealth 与节奏优化

优点：

- 不破坏现有稳定主线
- 翻译服务异常不会影响采集
- 审核体验最好
- 浏览器优化可单独回退

缺点：

- 产物更多
- 需要一层额外后处理流程

### 方案 2：把翻译直接并入 scrape

做法：

- 采集过程中同步翻译并直接写中文产物

优点：

- 命令表面上更少

缺点：

- 翻译服务不稳定会影响抓取
- 运行时间更长
- 出错边界混在一起，不利于排障

### 方案 3：只做 HTML，不做中文 CSV

做法：

- 保留英文 CSV
- 只新增 HTML 审核页

优点：

- 实现最轻

缺点：

- 员工导出、筛选、二次处理时仍然不友好
- 中文增强不能进入表格工作流

推荐采用方案 1。

## CLI 设计

### 保留现有命令

继续保留：

- `ali_mvp scrape ...`

职责不变：

- 抓取列表页
- 可选详情补全
- 黑名单过滤
- 写原始英文产物

### 新增后处理命令

新增：

- `ali_mvp postprocess --run-dir <run_dir>`

职责：

1. 读取指定 run 目录下已有产物
2. 生成中文增强 CSV
3. 生成 HTML 审核页
4. 写翻译缓存

建议后续可选参数：

- `--run-dir`
- `--translator`
- `--cache-file`
- `--html-title`

第一版只要求 `--run-dir`，其余保持默认即可。

## 输出设计

### 保留原始产物

现有文件继续保留：

- `products.csv`
- `products_filter_audit.csv`
- `category_rank.csv`

兼容要求：

- `products.csv` 字段顺序不变
- `products_filter_audit.csv` 旧字段不变
- `category_rank.csv` 结构不变

### 新增中文增强产物

新增：

- `products_zh.csv`
- `products_filter_audit_zh.csv`
- `products_report.html`

### 新增审核视图输入

为了不直接修改旧审计文件 schema，新增：

- `products_review.csv`

用途：

- 作为 `postprocess` 和 HTML 的统一输入
- 包含 accepted 与 rejected 的完整审核上下文
- 不承担原始底表职责

这样可以避免为了后处理强行扩展旧 `products_filter_audit.csv`，从而影响现有下游。

## 数据结构设计

### `products_zh.csv`

基于 `products.csv` 原字段，追加：

- `title_zh`
- `shop_name_zh`
- `promotion_text_zh`
- `attributes_summary`
- `attributes_summary_zh`

设计说明：

- `attributes_text` 往往较长且噪声较多，不建议整段直接翻译
- 第一版先做英文摘要，再翻译摘要
- `attributes_summary` 可由若干关键规格对或截断文本组成

### `products_filter_audit_zh.csv`

基于 `products_filter_audit.csv` 原字段，追加：

- `filter_decision_zh`
- `filter_stage_zh`
- `reject_groups_zh`
- `reject_terms_zh`
- `warning_groups_zh`
- `warning_terms_zh`
- `reason_zh`

设计说明：

- `reason_zh` 不依赖通用机器翻译
- `reason_zh` 优先由规则映射生成，确保稳定、可解释

例如：

- `battery / lithium / charger` -> `带电供电类`
- `remote control / controller / pcb / chip` -> `电子控制或芯片类`
- `sensor / ignition / timer switch` -> `电子元件或控制器类`

### `products_review.csv`

该文件用于人工审核视图，包含 accepted 与 rejected 两类记录，建议字段至少包括：

- `source_type`
- `source_value`
- `title`
- `product_url`
- `image_url`
- `price`
- `search_card_url`
- `entry_type`
- `is_promoted`
- `promo_channel`
- `promotion_text`
- `shop_name`
- `shipping_text`
- `attributes_text`
- `description_text`
- `detail_status`
- `filter_decision`
- `filter_stage`
- `reject_groups`
- `reject_terms`
- `reject_fields`
- `warning_groups`
- `warning_terms`
- `warning_fields`

设计说明：

- `products_filter_audit.csv` 保持机器审计口径
- `products_review.csv` 提供卡片化审阅所需上下文
- HTML 页面与中文增强逻辑优先消费 `products_review.csv`

## HTML 审核页设计

### 页面目标

`products_report.html` 的唯一核心目标是：

- 让员工快速确认黑名单是否误判、漏判

因此页面优先服务“审核”，不是服务复杂 BI。

### 页面结构

顶部 summary：

- total
- accepted
- rejected
- reject group 分布
- promo 数量
- detail 缺失数量

主体分两块：

1. Rejected
   - 默认优先展示
   - 用于检查误杀
2. Accepted
   - 用于抽查漏杀

### 卡片内容

每张卡片展示：

- 图片
- 标题英文
- 标题中文
- 价格
- 店铺英文
- 店铺中文
- promo 标记
- promotion 英文
- promotion 中文
- attributes 摘要英文
- attributes 摘要中文
- blacklist 判定结果
- 命中的 group / term / field
- `detail_status`

页面默认同时展示 accepted 与 rejected，但视觉重心应偏向 rejected。

## 翻译策略

### 翻译范围

当前只翻译以下字段：

- `title`
- `shop_name`
- `promotion_text`
- `attributes_summary`
- 黑名单命中说明

不要求第一版翻译整段 `description_text` 或整段 `attributes_text`。

### 翻译方式

翻译在采集完成后进行，由 `postprocess` 调用独立翻译模块。

要求：

- 最佳努力
- 翻译失败不终止整次后处理
- 失败字段回退英文

### 缓存策略

建议按文本哈希做缓存，避免重复翻译同一文本。

默认缓存文件：

- `<run_dir>/translation_cache.json`

这样每次 run 的增强结果可以单独归档、复现。

## 浏览器最小加固设计

### 目标

在现有 DrissionPage + 真实 Chrome profile 架构内，降低明显 automation 痕迹，让页面交互更像正常用户。

### 配置层

挂点：

- `ali_mvp/browser.py:_build_options(...)`

要求：

- 继续只使用项目目录内 profile：`E:\AliExpress\.browser-profile`
- 默认不手工硬编码 UA
- 优先保持 profile、浏览器版本、站点状态一致性

建议引入一个可回退的最小配置面：

- `--browser-hardening off|minimal`

默认值：

- `minimal`

### 页面初始化层

挂点：

- `open_listing_page(...)` 后新增页面初始化 helper

例如：

- `_init_page_stealth(page)`

第一版只做最小 JS 层收敛：

- `navigator.webdriver` 暴露收敛
- 少量 `navigator` / `permissions` 一致性修正

明确不做：

- 不做重型 canvas/webgl 指纹改写
- 不做大范围 prototype 污染
- 不做与真实 profile 明显冲突的伪造

### 行为节奏层

挂点：

- `_collect_current_page(...)`
- `_scroll_to_pagination(...)`
- `_go_to_next_page(...)`
- 详情页打开与恢复链路

建议新增 helper：

- `_sleep_jitter(min_s, max_s)`
- `_human_scroll_step(...)`
- `_pause_after_navigation(...)`

行为要求：

- 固定等待改为轻微抖动
- 滚动距离不总是固定值
- 翻页、打开详情页前后增加短暂停顿
- 页面已稳定时，不继续高频重复动作

### 站内导航一致性

详情打开策略继续遵循：

- 优先沿搜索卡片上下文进入详情
- 只有卡片进入失败时才走 direct fallback

原因：

- 页面跳转链更自然
- referer 与站内行为更接近真实用户
- promo / item 两类入口更容易按站点真实逻辑落页

### Challenge 页面处理

在以下节点增加轻量检测：

- 打开 listing 后
- 翻页后
- 打开 detail 后

若识别到 captcha / challenge / block 页：

- 暂停自动操作
- 等待人工恢复
- 恢复后再继续主线

这不是“自动解验证码”，而是避免脚本在 challenge 页继续乱点。

## 模块边界

### 新增模块

- `ali_mvp/postprocess.py`
  - 后处理编排
- `ali_mvp/translation.py`
  - 翻译适配、缓存、失败回退
- `ali_mvp/reporting.py`
  - HTML 页面渲染
- `ali_mvp/review.py`
  - 组装 `products_review.csv` 与审核视图记录

### 调整模块

- `ali_mvp/cli.py`
  - 增加 `postprocess` 子命令
  - 增加 `--browser-hardening` 参数
- `ali_mvp/output.py`
  - 增加 CSV reader / writer
  - 增加中文 CSV 与 HTML 输出 helper
- `ali_mvp/browser.py`
  - 加入最小 stealth 初始化
  - 加入节奏 helper
  - 将固定等待收敛为可控抖动

## 错误处理

### 后处理错误

- 单条翻译失败：回退英文，继续处理
- 缓存文件损坏：记录提示，允许重建缓存
- 输入文件缺失：明确报错并退出
- HTML 生成失败：不影响原始 CSV，但 `postprocess` 应返回失败码

### 浏览器侧错误

- 若 `browser-hardening=minimal` 逻辑失败，应尽量回退到现有可用行为
- 不允许因为 stealth 注入失败而阻止页面加载
- 不允许因为节奏 helper 引入无限等待

## 验证

### 兼容性验证

要求：

- 不运行 `postprocess` 时，现有 `scrape` 主产物保持兼容
- `products.csv` 字段顺序不变
- `products_filter_audit.csv` 旧字段不变
- `category_rank.csv` 结构不变

### 后处理验证

对同一次 run：

- `products_zh.csv` 行数等于 `products.csv`
- `products_filter_audit_zh.csv` 行数等于 `products_filter_audit.csv`
- `products_review.csv` 能覆盖 accepted 与 rejected 审核记录
- `products_report.html` 中 accepted / rejected 数量与 CSV 一致
- 翻译失败时，文件仍能生成，失败字段回退英文

### 浏览器回归验证

使用本项目 profile：

1. `scrape` 20 条，不带详情
2. `scrape` 20 条，带详情
3. `scrape` 50 条，带详情 + 黑名单
4. 对第 3 次结果运行 `postprocess`

重点确认：

- `detail_open_failed` 不回升
- accepted 数量无异常下滑
- 没有因为最小加固破坏翻页与详情链路
- HTML 审核页能直接帮助人工发现误判

## 风险与边界

### 风险

- 免费翻译服务可用性不稳定
- 过度 stealth 可能与真实站点脚本冲突
- HTML 展示字段过多时，页面可能偏重

### 控制策略

- 翻译仅做后处理，失败可回退
- 浏览器侧只做最小补丁，可随时关闭
- HTML 只围绕审核目标，不扩展为复杂报表系统

### 明确边界

- 本期不做全字段中文化
- 本期不做代理池
- 本期不做自动解验证码
- 本期不引入外部数据库或服务端报表系统

## 实施顺序建议

1. 先做 `postprocess` 主骨架与输出读写
2. 再做 `products_review.csv`
3. 再做中文增强 CSV
4. 再做 HTML 审核页
5. 最后做浏览器最小加固与回归验证

这样可以先交付人工审核价值，再逐步迭代风控稳定性。
