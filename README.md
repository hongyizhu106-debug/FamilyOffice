# 家族诊断问卷与报告系统

> **Family Office Diagnostic Survey & Report System**  
> 面向家族办公室顾问的结构化治理风险诊断平台

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-lightgrey)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red)](#授权说明)

---

## 项目简介

本系统通过网页问卷采集家族治理与风险指标数据，经 **奇点引擎（Singularity Engine）** 评分后，自动生成结构化诊断报告（PDF / HTML）。

**主要用户**：家族办公室顾问及其客户  
**核心质量目标**：数据完整性 · 评分准确性 · 报告可信度 · 系统安全性

---

## 系统架构

```
用户浏览器
    │
    ▼
┌─────────────────────────────────┐
│  Step 1 · Web 问卷层             │
│  Flask + CSRF + Auth + 跳题引擎  │
│  Web_survey_app.py               │
└────────────┬────────────────────┘
             │ 答卷 JSON
             ▼
┌─────────────────────────────────┐
│  Step 2 · 评分层  ⚙️ 核心算法    │
│  Singularity Engine              │
│  singularity_engine.py  *私有*   │
└────────────┬────────────────────┘
             │ 评分载荷
             ▼
┌─────────────────────────────────┐
│  Step 3 · 方法论索引              │
│  PDF 抽取 · 规则索引              │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  Step 4 · 报告层  ⚙️ 核心模板    │
│  report_generator.py  *私有*     │
│  HTML → PDF 输出                 │
└─────────────────────────────────┘
```

各层严格单向依赖，禁止跨层调用。

---

## 目录结构

```
FamilyOffice/
├── launch.pyw                      # 图形启动器（双击运行）
├── start.py                        # 命令行启动器
├── 一键启动.command                 # macOS 双击启动脚本
├── 一键启动-Web版问卷与报告.bat      # Windows 双击启动脚本
│
└── RowData/                        # 核心系统
    ├── requirements.txt            # Python 依赖清单
    │
    ├── MainController/
    │   ├── MacinController.py      # 入口：启动 Flask，预检依赖
    │   └── AdminApp/               # 管理后台（FastAPI，独立服务）
    │
    ├── Step1/                      # 问卷层（全部公开）
    │   ├── Constructor/
    │   │   ├── Web_survey_app.py   # Flask 应用主体（路由/认证/CSRF）
    │   │   ├── Survey_cli.py       # 命令行问卷工具
    │   │   └── Build_question_bank.py
    │   ├── Data/
    │   │   ├── Question_bank.json  # ⚠️ 622 题题库（私有，需单独获取）
    │   │   ├── jump.json           # ⚠️ 跳题逻辑（私有，需单独获取）
    │   │   └── indicator_singularity_map.json
    │   └── Tools/
    │
    ├── Step2/                      # 评分层
    │   ├── Constructor/
    │   │   └── singularity_engine.py  # ⚠️ 核心评分引擎（私有，需单独获取）
    │   ├── Data/
    │   │   ├── indicator_singularity_map.json
    │   │   └── indicator_fx_rules.json
    │   └── Tools/
    │       ├── backtest_singularity.py
    │       └── report_singularity_map_coverage.py
    │
    ├── Step3/                      # 方法论索引层（全部公开）
    │   ├── extract_step3_pdf.py
    │   └── STEP3_UNDERSTANDING.md
    │
    └── Step4/                      # 报告层
        ├── report_generator.py     # ⚠️ 报告生成器（私有，需单独获取）
        ├── report_spec.py          # ⚠️ 报告规格定义（私有，需单独获取）
        ├── validate_report.py      # 报告校验工具（公开）
        └── templates/
```

> **⚠️ 标注的文件** 属于核心算法与专有数据，未随仓库分发，需联系作者授权获取。

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/hongyizhu106-debug/FamilyOffice.git
cd FamilyOffice
```

### 2. 安装依赖

```bash
pip install -r RowData/requirements.txt
```

### 3. 获取私有文件

将以下 5 个文件放到对应目录（需联系授权获取）：

| 文件 | 放置路径 |
|---|---|
| `singularity_engine.py` | `RowData/Step2/Constructor/` |
| `report_generator.py` | `RowData/Step4/` |
| `report_spec.py` | `RowData/Step4/` |
| `Question_bank.json` | `RowData/Step1/Data/` |
| `jump.json` | `RowData/Step1/Data/` |

### 4. 启动服务

**方式一：图形界面（推荐）**
```bash
python launch.pyw
```

**方式二：命令行**
```bash
python start.py
```

**方式三：macOS 双击**  
Finder 中双击 `一键启动.command`

浏览器访问 `http://127.0.0.1:5000/`，访问密码：`familyoffice`

---

## 核心模块说明

### Web 问卷层（Step 1）

- **认证**：HMAC Cookie 签名 + 访问密码
- **CSRF 保护**：所有 POST 路由均校验 CSRF token
- **跳题引擎**：基于 `jump.json` 的两级跳题（维度级 → 类型级）
- **限流**：默认 60 req/min
- **会话持久化**：答题进度写入本地 JSON，支持断点续答

### 评分层（Step 2）—— 私有

奇点引擎（Singularity Engine）将答卷权重映射为多维奇点评分，输出：
- `singularity_stage_a`：指标层得分
- `singularity_stage_b`：维度聚合得分 + 风险分级
- 完整评分追踪链路（`with_trace` 模式）

### 报告层（Step 4）—— 私有

接受评分载荷，渲染 HTML 诊断报告，支持导出 PDF。  
`validate_report.py` 为公开的报告结构校验工具。

---

## 安全设计

- 路径遍历防护：`/artifacts/<filename>` 路由内置路径校验
- 密码不记录日志，不出现在 HTTP 响应中
- 客户答卷文件（`Rubbish/`）已从 Git 历史排除
- 环境变量管理密钥，禁止硬编码

---

## 依赖环境

| 包 | 用途 |
|---|---|
| `flask >= 3.0` | Web 框架 |
| `pandas >= 2.2` | 数据处理 |
| `openpyxl >= 3.1` | Excel 读写 |
| `fpdf2 >= 2.7` | PDF 生成 |
| `pymupdf >= 1.24` | PDF 解析 |
| `weasyprint >= 62.0` | HTML → PDF 渲染 |
| `pdfplumber >= 0.11` | PDF 文本提取 |
| `fastapi / uvicorn` | AdminApp 子服务 |

---

## 授权说明

本仓库公开的部分（启动脚本、流程框架、工具脚本）采用 MIT 协议。  
核心算法（`singularity_engine.py`）、题库数据及报告模板为专有资产，**未经授权不得复制或商业使用**。

如需完整授权，请联系作者。
