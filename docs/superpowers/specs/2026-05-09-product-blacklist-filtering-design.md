# AliExpress 商品黑名单过滤设计

日期：2026-05-09

## 目标

在现有采集与详情增强流程之后，增加一层商品准入过滤。该过滤只做黑名单剔除，不做白名单扩展：

- 搜索 `keyword` 本身视为正向范围
- 黑名单用于拒绝高危或不符合要求的商品，例如带电、芯片、PCB 一类商品
- 过滤后的 `products.csv` 只保留通过商品
- 同时保留完整审计输出，记录被拒绝与被警告的商品及原因

## 现状证据

当前流程是：

1. 抓取列表页商品
2. 可选进入详情页补字段
3. 归一化成 `ProductRecord`
4. 直接写出 `products.csv` 与 `category_rank.csv`

当前没有任何入库前过滤能力，因此：

- 不符合目标特征的商品会直接进入最终产物
- 无法用规则稳定剔除“带电 / 芯片 / PCB”等高风险类商品
- 也没有审计文件解释“为什么某个商品被剔除”

## 方案

### 总体流程

在 `normalize_products()` 之后、写 CSV 之前增加过滤步骤：

1. 先按现有逻辑得到 `products: list[ProductRecord]`
2. 对每个商品执行黑名单匹配
3. 生成两类输出
   - accepted products
   - filter audit rows
4. `products.csv` 只写 accepted products
5. `category_rank.csv` 只基于 accepted products 计算
6. 新增 `products_filter_audit.csv`，写出全部商品的过滤决策

### 过滤语义

只支持黑名单，不支持白名单。

每个商品会得到三类信息：

- `accepted`：未命中强拒绝规则，可进入 `products.csv`
- `rejected`：命中强拒绝规则，不进入 `products.csv`
- `warning`：命中弱字段风险词，但不足以单独拒绝；仍进入 `products.csv`，但写入审计表

### 字段分层

为避免“商品本体只是支架/配件，但描述里提到适配某种电器”而误杀，匹配字段采用分层策略。

#### 强字段

以下字段命中黑名单词时，直接拒绝：

- `title`
- `attributes_text`

原因：

- 这两个字段更接近商品本体属性
- 若其中明确出现 `battery`、`pcb`、`charger` 等词，通常更可信

#### 弱字段

以下字段命中黑名单词时，不单独拒绝，只记 warning：

- `breadcrumb`
- `description_text`

原因：

- 这两个字段更容易出现兼容设备、营销说明、类目环境描述
- 尤其是配件类商品，描述区可能大量出现电器名称，但商品本体并不属于禁入类别

该策略的核心目标是：

- 优先拦商品本体是禁入类的商品
- 降低“支架 / 垫片 / 防尘罩 / 外壳 / 收纳配件”因描述提到电器而被误判的概率

### 规则来源

支持两层来源叠加：

#### 1. 规则文件

新增 CLI 参数：

- `--blacklist-file <path>`

规则文件用于长期维护，建议放在仓库内，例如：

- `rules/product_blacklist.json`

示例格式：

```json
{
  "version": 1,
  "groups": [
    {
      "name": "electrical_power",
      "terms": ["battery", "lithium battery", "rechargeable", "charger", "power bank"]
    },
    {
      "name": "chip_pcb",
      "terms": ["chip", "ic", "integrated circuit", "pcb", "pcba", "circuit board", "motherboard"]
    }
  ]
}
```

#### 2. CLI 临时补充

新增可重复参数：

- `--reject-keyword <term>`

可多次传入，例如：

```bash
python -m ali_mvp scrape --keyword "Home appliance accessories" --blacklist-file rules/product_blacklist.json --reject-keyword sensor --reject-keyword relay
```

CLI 补充词会并入运行时规则集，并统一归到一个逻辑组，例如：

- `cli_extra`

### 匹配方式

第一版使用大小写不敏感的简单包含匹配。

规则：

- 若 term 命中强字段，记为 reject hit
- 若 term 只命中弱字段，记为 warning hit
- 同一商品可命中多个 group / term / field
- 输出时对重复命中去重

第一版不支持：

- 正则
- 词边界控制
- 多词联合条件
- 例外词 / 否定词

这样先保持规则系统简单、可解释、容易维护。

## 输出

### 现有主产物

`products.csv`

- 只包含 `accepted` 商品
- warning 商品仍保留在其中

`category_rank.csv`

- 只基于 `accepted` 商品聚合

### 新增审计文件

新增：

- `products_filter_audit.csv`

该文件包含全部商品，包括 accepted 与 rejected。

建议字段：

- `source_type`
- `source_value`
- `title`
- `product_url`
- `filter_decision`
- `reject_groups`
- `reject_terms`
- `reject_fields`
- `warning_groups`
- `warning_terms`
- `warning_fields`

其中：

- `filter_decision`：`accepted` 或 `rejected`
- `reject_*`：仅强字段命中时填写
- `warning_*`：仅弱字段命中时填写

### 审计解释性

这份审计表的目的是让后续规则调整有依据：

- 哪些商品被拒绝
- 是因为哪一组规则被拒绝
- 命中了哪些词
- 命中了哪些字段
- 哪些商品虽然保留，但存在弱字段风险信号

## 代码边界

建议新增独立模块，例如：

- `ali_mvp/filtering.py`

职责拆分：

- 规则加载
- CLI 补充词合并
- 商品文本提取与字段分层
- 黑名单匹配
- accepted / audit 拆分

这样避免把过滤逻辑塞进 `cli.py` 或 `extractor.py`，便于后续扩展。

### 建议挂点

- `cli.py`
  - 解析 `--blacklist-file`
  - 解析 `--reject-keyword`
  - 在 `normalize_products()` 之后调用过滤
- `output.py`
  - 增加 `write_filter_audit_csv()`
- `scoring.py`
  - 保持现有 `ProductRecord` 不变，过滤审计可用独立 dataclass 或简单字典行

## 边界

- 不改变抓取与详情增强顺序；过滤发生在商品归一化之后
- 不做白名单
- 不根据 `shop_name`、`shipping_text`、`promotion_text` 触发拒绝
- 不让 `description_text` 或 `breadcrumb` 单独决定拒绝
- 不在第一版实现复杂规则系统

## 风险与重点验证

本阶段最重要的验证点不是“能不能拒绝”，而是“会不会误杀配件类商品”。

重点验证：

1. 标题命中黑名单时会拒绝
2. 属性命中黑名单时会拒绝
3. 仅 `description_text` 命中时不会拒绝，只产生 warning
4. 仅 `breadcrumb` 命中时不会拒绝，只产生 warning
5. “支架 / 垫片 / 罩子 / 外壳 / 配件”类商品，即使描述中提到洗衣机、冰箱、家电，也不应被自动拒绝
6. CLI 补充词与规则文件能同时生效
7. 未提供规则文件且未传 CLI 规则时，行为应与当前版本一致

## 验证

- `tests/test_cli.py`
  - `--blacklist-file` 可解析
  - `--reject-keyword` 可重复解析
- `tests/test_filtering.py`
  - 强字段命中会拒绝
  - 弱字段命中只 warning
  - CLI 补充词会进入规则集
  - 无规则时不改变结果
- `tests/test_output.py`
  - `products_filter_audit.csv` 能正确写出
- 手工验证
  - 使用 `Home appliance accessories`
  - 人工挑选“支架 / 防尘罩 / 垫脚”类商品，确认不会因描述提到家电而误拒
  - 人工挑选明显带电 / 芯片 / PCB 类商品，确认会被拒绝并写入审计表
