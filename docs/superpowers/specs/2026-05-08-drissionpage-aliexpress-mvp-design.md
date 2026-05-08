# DrissionPage AliExpress 选品验证 MVP 设计

日期：2026-05-08

## 目标

构建一个本地 Python MVP，用 DrissionPage 打开 AliExpress 搜索页或用户提供的页面 URL，在用户已人工登录的浏览器状态下采集商品列表数据，并输出 CSV，用于快速验证选品逻辑。

第一版重点是验证“某个关键词或入口页是否值得继续选品”，不是构建稳定的大规模采集系统，也不承诺获取 AliExpress 官方热销榜。

## 范围

包含：

- CLI 支持关键词入口和 URL 入口。
- 复用人工登录后的浏览器状态。
- 打开页面、滚动加载、提取商品卡片字段。
- 输出商品明细 CSV。
- 按入口聚合一个简单热度评分 CSV。
- 为纯逻辑部分添加自动化测试。

不包含：

- 代理池、验证码处理、账号池。
- 官方 API 接入。
- 大规模并发采集。
- 强制识别 AliExpress 真实后台类目树。
- 自动购买、下单或账号操作。

## CLI

目标命令：

```bash
python -m ali_mvp scrape --keyword "women dress" --max-items 80
python -m ali_mvp scrape --url "https://www.aliexpress.com/..." --max-items 80
```

参数：

- `--keyword`：生成 AliExpress 搜索 URL。
- `--url`：直接打开用户提供的 AliExpress URL。
- `--max-items`：最多采集商品数，默认 80。
- `--output-dir`：输出目录，默认 `data`。

`--keyword` 和 `--url` 互斥，必须提供其中一个。

## 数据字段

`products.csv`：

- `source_type`：`keyword` 或 `url`
- `source_value`：关键词或 URL
- `title`
- `price`
- `sold_count`
- `rating`
- `review_count`
- `product_url`
- `image_url`
- `scraped_at`

`category_rank.csv` 第一版按 `source_value` 聚合，不强行解析真实类目：

- `source_value`
- `product_count`
- `total_sold_count`
- `avg_rating`
- `avg_review_count`
- `heat_score`

## 架构

```text
ali_mvp/
  __init__.py
  cli.py
  browser.py
  extractor.py
  scoring.py
  output.py
tests/
  test_scoring.py
  test_output.py
requirements.txt
README.md
```

职责：

- `cli.py`：解析参数，组织主流程。
- `browser.py`：封装 DrissionPage 页面启动、导航、滚动。
- `extractor.py`：从页面 DOM 提取商品数据，并做字段归一化。
- `scoring.py`：销量、评分、评价数解析和热度聚合。
- `output.py`：写入 CSV。

## 数据流

```text
CLI 参数
  -> 构造 source
  -> 打开或复用浏览器页面
  -> 导航到搜索/类目页面
  -> 滚动加载
  -> 提取商品卡片
  -> 标准化字段
  -> 写 products.csv
  -> 聚合热度
  -> 写 category_rank.csv
```

## 错误处理

- 参数错误：直接退出并显示 argparse 错误。
- 页面打开失败：输出明确错误，提示用户确认网络、登录态或 URL。
- 没采到商品：生成空 CSV 表头，并提示可能原因包括页面结构变化、地区跳转、验证码、未登录或选择器失效。
- 单个商品字段缺失：保留该商品，缺失字段为空或 0，不中断整体采集。

## 测试策略

自动化测试覆盖纯逻辑：

- 销量文本解析，例如 `1,000+ sold`、`2.3K sold`。
- 评分和评价数解析。
- 热度聚合规则。
- CSV 写入表头和基本行内容。

浏览器采集部分通过人工验证：

- 用户先在浏览器中登录 AliExpress。
- 运行一个关键词采集命令。
- 检查 `data/products.csv` 至少有商品行。
- 检查 `data/category_rank.csv` 生成热度汇总。

## 限制和风险

- AliExpress 页面结构、语言、地区和 AB 测试会影响字段提取。
- DrissionPage 适合快速验证，不作为长期稳定生产采集的唯一依赖。
- 如果页面触发验证码或风控，第一版只提示用户人工处理，不做绕过。
- DrissionPage 的商业使用授权需要单独确认；本 MVP 按内部验证用途设计。

