# AliExpress 商品详情增强设计

日期：2026-05-09

## 目标

在现有列表页批量采集能力之上，增加一个可选的详情增强模式。开启后，系统在得到最终商品集合后进入每个商品详情页，补充更完整的商品字段，并把结果写入 `products.csv`。

## 现状证据

当前实现主要采集列表页卡片信息：

- `title`
- `price`
- `sold_count`
- `rating`
- `review_count`
- `product_url`
- `image_url`

当前唯一的详情页能力是一个可选的评分补全逻辑，只在显式开启时访问少量详情页补 `rating`。这不足以覆盖商品详情页里的店铺、运费、属性、描述等高价值信息。

## 方案

### CLI 入口

- 新增 `--enrich-detail`
  - 开启商品详情页增强
- 删除 `--enrich-detail-rating`
- 删除 `--detail-limit`

详情增强不再做“前 N 个商品”的限制。数量控制统一由 `--max-items` 决定：最终保留下来的商品有多少个，就进入多少个详情页补数据。

### 详情增强流程

1. 先按现有逻辑完成列表页采集、分页、去重与总量截断
2. 得到最终商品集合后，逐个进入商品详情页
3. 从详情页提取新增字段
4. 详情页失败时，该商品新增字段留空，不中断整批任务
5. 返回列表页继续处理下一个商品，直至全部完成

### 新增字段

开启 `--enrich-detail` 后，`products.csv` 在现有字段基础上新增：

- `shop_name`
- `shipping_text`
- `detail_rating`
- `detail_review_count`
- `breadcrumb`
- `attributes_text`
- `description_text`

字段格式约定：

- `breadcrumb`：扁平文本，例如 `Home > Kitchen > Parts`
- `attributes_text`：JSON 字符串，保存详情页属性区的键值对
- `description_text`：完整纯文本，不保留 HTML

### 与现有字段的关系

保留列表页字段：

- `rating`
- `review_count`

新增详情页字段：

- `detail_rating`
- `detail_review_count`

第一版不做字段覆盖合并。列表值和详情值同时保留，方便后续核对质量和决定是否以详情页为准。

## 边界

- 不做并发详情抓取。
- 不抓原始 HTML 描述。
- 不新增独立详情 CSV；仍写入现有 `products.csv`。
- 不承诺所有详情页字段都稳定存在；缺失时允许为空。

## 兼容性影响

- `--enrich-detail-rating` 将被移除。
- `--detail-limit` 将被移除。
- README、帮助文案、测试都需要同步更新。

这是一个有意的 CLI 收敛：把原先“只补评分”的可选能力升级成“统一详情增强”能力。

## 验证

- `tests/test_cli.py`
  - `--enrich-detail` 可解析
  - `--enrich-detail-rating` 不再存在
  - `--detail-limit` 不再存在
- `tests/test_browser.py`
  - 详情增强关闭时，不进入商品详情页
  - 详情增强开启时，会对最终商品集合逐个访问详情页
  - 单个详情页失败不会中断整批流程
  - 详情页提取结果会合并回原始商品字典
- `tests/test_output.py`
  - 新增字段会写入 `products.csv`
- 手工验证
  - 使用当前目录 `.browser-profile`
  - 运行 `--enrich-detail`，检查输出中新增字段不为空
  - 重点检查 `attributes_text` 是否为合法 JSON 字符串
  - 重点检查 `description_text` 是否为纯文本
