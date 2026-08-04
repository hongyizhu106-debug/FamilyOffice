# PlanA - 财务数据输出规范（PDF）

本目录定义 **“每次运行后生成 PDF 报告”** 的统一输出规范（口径 + 版式 + 文件产物约定）。

- 目标：把 MCP 工具返回的财务数据，按固定结构渲染为 **一份可分享/可打印的 PDF**。
- 适用范围：
  - 境内财报（A 股：Tushare `income/balancesheet/cashflow/fina_indicator`）
  - 港股/美股财报（Tushare `hk_*` / `us_*`）

## 快速索引

- 规范总览：见 [spec/OUTPUT_SPEC.md](spec/OUTPUT_SPEC.md)
- 口径与计算：见 [spec/METRICS_AND_YOY.md](spec/METRICS_AND_YOY.md)
- 输入/输出 JSON Schema：见 [spec/REPORT_JOB_SCHEMA.json](spec/REPORT_JOB_SCHEMA.json)
- 示例：见 [examples/EXAMPLE_REPORT_JOB.json](examples/EXAMPLE_REPORT_JOB.json)

## 约定

- 本规范只定义“长什么样/怎么算/产物叫什么”，不绑定具体实现技术。
- 实现侧建议：先生成 HTML（含 CSS），再导出 PDF（Chromium 打印）。
