# 2026-05-10 blacklist baseline archive

## Status

截至 2026-05-10，AliExpress 当前黑名单规则已收敛到新的业务口径：

- 目标范围：**广义家电配件**
- 当前黑名单原则：**只禁带电、带芯片、带电子控制属性的商品**
- 不再因为“看起来偏耗材/周边/罩子/滤芯/支架”就直接拒绝

当前结论：**这版规则可以作为阶段性基线冻结，后续只在出现新样本证据时再继续细化。**

## Rule boundary

### 应允许进入结果集的商品

以下类型当前应默认允许：

- 吸尘器耗材、刷头、边刷、滤网、尘袋
- 冰箱/净水类滤芯
- 洗衣机/冰箱/烘干机防尘罩、盖布、门挡
- 搅拌机、料理机、Thermomix 一类的非电控配件
- 各类支架、防震垫、导流件、盖板、保护件

### 应拒绝的商品

以下类型属于当前黑名单重点：

- 供电/储能类：电池、充电器、电源适配器、电源模块
- 控制/遥控类：遥控器、智能开关、控制器、继电器、传感器
- 芯片/板卡类：chip / ic / pcb / pcba / motherboard / circuit board
- 点火/电控零件：igniter、timer switch、rotary knob timer
- 明显设备类：美容仪、治疗仪、蒸汽清洗机

## Current matching model

当前实现位于 `ali_mvp/filtering.py`，分两段执行：

1. `prefilter_listing_products(...)`
   - 只看搜索卡片标题
   - 用 `pre_reject_terms` 做 listing 阶段直接拒绝
2. `filter_products(...)`
   - 详情补全后再判断
   - `title + attributes_text` 可触发拒绝
   - `breadcrumb + description_text` 只作为 warning，不直接拒绝

### require_terms 机制

当前 `FilterGroup` 支持：

- `pre_reject_terms`
- `post_reject_terms`
- `pre_require_terms`
- `post_require_terms`

含义是：

- 命中 `reject_terms` 只是第一步
- 如果该组配置了 `require_terms`，则还必须在同一商品文本上下文内再命中任一 `require_term`
- 只有 `reject + require` 同时成立，才会进入黑名单

这个机制主要用于压缩“语义太宽的词”带来的误伤。

## Active rule groups

当前规则文件：`rules/product_blacklist.json`

当前保留的组：

- `electrical_power`
- `relay_switch_sensor`
- `chip_pcb`
- `remote_control_device`
- `ignition_control`
- `medical_therapy`
- `steam_cleaner_device`
- `beauty_device`
- `appliance_timer_switch`

当前已明确移除的过宽组：

- `robot_vacuum_spares`
- `water_filter_consumable`
- `laundry_cover_textile`

移除原因：这些商品虽然可能不是最理想的目标品，但**不符合“带电/带芯片/电控”黑名单口径**，继续保留会产生明显误杀。

## Special note: medical_therapy

`medical_therapy` 是本轮重点收窄的规则组。

### 旧问题

仅依赖 `massager`、`therapy`、`rehabilitation` 这类词会误伤：

- 手动按摩滚轮
- 非电动理疗类工具
- 标题里只是带泛化“therapy/massage”营销词的商品

### 当前策略

`medical_therapy` 现在要求：

- 先命中治疗/按摩类 reject 词
- 再命中设备/电气信号 require 词

当前 require 信号包括：

- `machine`
- `device`
- `instrument`
- `usb`
- `rechargeable`
- `electric`
- `electrical`
- `ems`
- `rf`
- `infrared`
- `laser`
- `magnetic`
- `stimulator`
- `220v`
- `110v`

### 结果

因此当前行为是：

- `Manual fascia massager roller` → **放行**
- `USB neck massager device` → **拒绝**
- `... Therapy Machine ...` → **拒绝**
- `... Rehabilitation Instrument ...` → **拒绝**
- `... Infrared Light Therapy ...` → **拒绝**

注意：`magnetic` 本身不会单独触发拒绝；它只是 `medical_therapy` 的 require 信号。若商品没有先命中 `massager/therapy/rehabilitation/stimulation` 等 reject 词，仍不会被误伤。

## Local replay validation

本轮使用的稳定样本：

- `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/products.csv`

按当前规则做本地回放后的结果：

- total: `50`
- accepted: `47`
- rejected: `3`

### Rejected samples

当前被拒绝的 3 个样本：

- `Microwave oven 11 mm long plastic spool rotary knob timer`
- `1Pcs Dryer Timer Timing Switch For Dyer Washing Machine DFJ-A 180 Minutes 250V/15A`
- `Dcool Portable Facial Beauty Machine with Cold Hot EMS Skin Strengthening Anti-Swelling Electroporation for Home Use And Salon`

命中组：

- `appliance_timer_switch`: `2`
- `beauty_device`: `1`

### Confirmed accepted boundary samples

当前已确认放行的边界样本包括：

- `Fit For Cecotec Conga ... Filter Dust Bag`
- `Refrigerator Water Filter Compatible with EDR2RXD1 ...`
- `Gray Top-Load Washing Machine Cover ...`
- `Steam Deflector for Thermomix TM7 ...`
- `Egg Steam Pan for Thermomix TM6 TM5 TM31 ...`
- `Magnetic Washing Machine Door Stop ...`

这些样本说明：

- “vacuum / filter / cover” 不再被粗暴拉黑
- `steam_cleaner_device` 只拦“蒸汽清洗机”，不会误伤普通 `steam` 配件
- `medical_therapy` 的 require 机制没有误伤普通 `magnetic` 配件

## Test coverage

与当前规则口径直接相关的测试集中在：

- `tests/test_filtering.py`

覆盖点包括：

- repository blacklist 对明显电控/设备类标题的预过滤
- repository blacklist 对吸尘器耗材 / 水滤芯 / 防尘罩的放行
- repository blacklist 对美容仪 / 定时开关的拒绝
- `require_terms` 的加载与生效
- `medical_therapy` 对手动按摩工具放行、对 USB / machine / device 类治疗设备拒绝

## Operational recommendation

当前建议：

- 以这版 `rules/product_blacklist.json` 作为阶段性基线
- 不再继续凭主观感觉扩黑名单词
- 后续只有在新增实站样本出现明确误杀/漏拦证据时，才继续做最小修正
- 优先用本地样本回放验证，再决定是否需要再跑实站

## Verification basis

本归档基于以下文件与验证结果整理：

- `rules/product_blacklist.json`
- `ali_mvp/filtering.py`
- `tests/test_filtering.py`
- `data/live-detail-recovery-50-project-profile/home-appliance-accessories/20260510_203753/products.csv`
