# PlanA 指标口径与同比计算

## 1. 指标字典（核心）

以下为报告必须覆盖的核心指标与取数优先级：

### 1.1 利润表（Income）
- 营业总收入 / 营收
- 利润总额
- 净利润

### 1.2 资产负债表（Balance Sheet）
- 资产合计（总资产）
- 负债合计（总负债）
- 所有者权益合计 / 股东权益

### 1.3 现金流量表（Cash Flow）
- 经营活动产生的现金流量净额（经营现金流）

### 1.4 比率/能力（Ratios）
- 资产负债率(%)：
  - 公式：`总负债 / 总资产 * 100`
- 流动比率、速动比率（若能取到）
- 毛利率(%)、净利率(%)、ROE(%)、ROA(%)（若能取到）

---

## 2. 同比（YoY）定义

### 2.1 年报同比

- 当前：`YYYY1231`（年报）
- 对比：`(YYYY-1)1231`

同比(%)：

$$\text{YoY\%} = (\frac{current}{previous} - 1) \times 100$$

边界：
- `previous == 0` 或缺失：显示 `—`
- `previous` 为负数时仍按公式计算（保持一致口径，不做绝对值修正）

### 2.2 季报同比（季度同比）

- 当前季度报告期：`YYYY0331 / YYYY0630 / YYYY0930 / YYYY1231`
- 对比：上一年同季度（例如 20250930 对比 20240930）

同比(%) 同上。

---

## 3. 展示规则

- 同比作为独立行展示，名称固定：`同比(%)`
- 若同一分组内多项指标都有同比，可在分组末尾给出“同比摘要表”。

---

## 4. 与现有 MCP 工具对接建议

- A 股：优先使用 `company_performance` 的
  - `income_basic` / `income_all`
  - `balance_basic` / `balance_all`
  - `cashflow_basic` / `cashflow_all`
  - `indicators`（其中包含 `debt_to_assets` 等）
- 港股/美股：用 `company_performance_hk/us` 的 `income/balance/cashflow/indicator`（若有）

生成报告时要把“本期 + 对比期”两期数据都取到，再统一算同比。
