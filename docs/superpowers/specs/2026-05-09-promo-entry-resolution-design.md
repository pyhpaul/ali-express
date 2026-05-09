# AliExpress Promo 入口商品解析设计

日期：2026-05-09

## 目标

支持搜索结果中的 `Dollar Express / BundleDeals2` promo 卡片：

- 搜索页把 promo 卡片当作有效命中项保留下来
- 不展开 promo 页里的全部商品
- 只追搜索命中的入口商品
- 若能还原真实 item 详情页，则继续抓详情
- 同时保留 promo 信号，如 `Dollar Express`、`Free shipping on 3 items`

## 现状证据

当前列表提取只抓 `/item/` 链接，因此会漏掉这类卡片：

- 搜索卡片 href：`/ssr/300000512/BundleDeals2?...`
- 页面类型：`Bundle Deals 2.0`
- 页面头部信号：
  - `Dollar Express`
  - `Free shipping on 3 items`
  - `Free returns`
  - `Buy more,save more`

同时，promo URL 里可以拿到入口商品上下文：

- `productIds=<item_id>:<sku_id>`
- `utparam-url=...x_object_id:<item_id>...`

已实测：可据此还原真实详情页 `https://www.aliexpress.com/item/<item_id>.html`

## 方案

### 搜索页采集

列表页同时识别两类卡片：

- `item_card`
  - href 为 `/item/...`
- `promo_card`
  - href 为 `/ssr/.../BundleDeals2...`

每条记录保留：

- 搜索卡片标题、价格、销量、评分、图片
- `entry_type`
- `search_card_url`
- `resolved_product_url`
- `promo_landing_url`
- `is_promoted`

其中：

- 普通卡片：`resolved_product_url == search_card_url`
- promo 卡片：`resolved_product_url` 由 promo URL 参数还原

### promo 详情增强

开启 `--enrich-detail` 后：

1. 若为普通 `item_card`，沿用现有详情增强逻辑
2. 若为 `promo_card`
   - 先打开 `promo_landing_url`
   - 提取 promo 信号
   - 再打开 `resolved_product_url`
   - 抓实际商品详情

不展开 promo 页里其它商品。

### 新增输出字段

在 `products.csv` 增加：

- `entry_type`
- `search_card_url`
- `is_promoted`
- `promo_channel`
- `promotion_text`
- `promo_landing_url`

字段约定：

- `entry_type`：`item_card` 或 `promo_card`
- `is_promoted`：是否属于 promo 落地逻辑
- `promo_channel`：例如 `Dollar Express`
- `promotion_text`：例如 `Free shipping on 3 items | Free returns | Buy more,save more`
- `promo_landing_url`：promo 页 URL；普通卡片为空

## 边界

- 不把 promo 页内所有商品当作搜索候选商品
- 不新增独立 promo CSV
- 真实 item URL 无法还原时，保留搜索卡片记录，但详情字段允许为空

## 验证

- `tests/test_browser.py`
  - promo 卡片会被识别
  - promo URL 能还原真实 item URL
  - promo 增强时会先抓 promo 信号再抓 item 详情
- `tests/test_extractor.py`
  - promo 元数据会进入 `ProductRecord`
- `tests/test_output.py`
  - 新增 promo 字段会写入 CSV
- 手工验证
  - 使用 `.browser-profile + 9333`
  - 搜索 `Home appliance accessories`
  - 确认 `Dollar Express` 卡片被写入
  - 确认 `product_url` 为真实 item URL
  - 确认 `promotion_text` 含 `Free shipping on 3 items`
