# 2026-05-10 detail chain stability archive

## Status

截至 2026-05-10，AliExpress 详情抓取主链路在项目专用 Chrome profile `E:\AliExpress\.browser-profile` 下已完成一轮可复核归档。

- 实站验证通过：`50` 条
- 验证样本来源：`Home appliance accessories`
- 当前结论：**抓取主链路可视为稳定版本，建议冻结；后续工作重点转向黑名单规则精修。**

## Verified result set

- profile: `E:\AliExpress\.browser-profile`
- output root: `data/live-detail-recovery-50-project-profile`
- category output:
  - `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753`
- key files:
  - `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/products.csv`
  - `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/products_filter_audit.csv`
  - `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/category_rank.csv`

## Key metrics

基于 `products.csv` 的 50 条已落盘结果：

- `detail_open_failed`: `0`
- `listing_context_failed`: `0`
- `captcha_blocked`: `0`
- `shop` 覆盖率: `50 / 50 = 100.0%`
- `attributes` 覆盖率: `50 / 50 = 100.0%`
- `description` 覆盖率: `50 / 50 = 100.0%`

补充上下文：

- `products_filter_audit.csv` 总审计条数：`63`
- 其中 listing 阶段直接拒绝：`9`
- 进入最终 `products.csv` 并完成详情补全：`50`

## Stable interpretation

这轮结果说明：

1. 在项目专用 profile 下，当前 item 详情打开与返回链路没有出现 `detail_open_failed` 或 `listing_context_failed`。
2. `shop_name`、`attributes_text`、`description_text` 已具备稳定落盘能力。
3. 详情补全链路当前不应继续频繁调整；继续改抓取链路的收益低，回归风险更高。

## Current recommendation

- **冻结抓取主链路**：以本次验证结果作为当前稳定归档基线。
- **后续重点转向黑名单规则精修**：
  - 提升 `attributes_text` 命中质量与规则解释性
  - 针对高风险整机/设备类词做更细粒度规则
  - 继续利用 `description_text` 作为 warning / 辅助信号，而不是重新打开抓取链路改造

## Verification basis

本归档基于仓库内现有产物核对完成：

- `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/products.csv`
- `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/products_filter_audit.csv`
