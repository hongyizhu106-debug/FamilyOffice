# Step1 总结（母文件夹）

这个 `Step1/` 是当前阶段的“母文件夹”，后续所有数据读取/写入都以它作为项目根目录。

## 目录结构

- `Step1/Constructor/`
  - 构造器与工具脚本（题库构建、映射规范化、Web 问卷等）
- `Step1/Data/`
  - 原始数据与题库
  - 主要文件：`Question_bank.json`
- `Step1/Env/`
  - Python 虚拟环境（已随 Step1 迁移）
- `MainController/`（独立启动器，位于 Step1 外）
  - 启动入口（例如一键启动 Web）
- `Step1/Rubbish/`
  - 运行产生的输出（web_response_*.json、web_progress_*.json 等）

## 常用入口

- 启动 Web 问卷（推荐）
  - 运行：`MainController/Start_Web.bat`
  - 浏览器打开：`http://127.0.0.1:5000/`

- 直接运行 Web 应用（调试用）
  - `Step1/Env/Scripts/python.exe Step1/Constructor/Web_survey_app.py`

- 题库映射规范化（同名同编码）
  - `Step1/Env/Scripts/python.exe Step1/Constructor/Normalize_mappings.py`
  - 只看统计不改文件：`... Normalize_mappings.py --report`

## 数据约定（Web 导出）

Web 提交结果保存在 `Step1/Rubbish/web_response_*.json`，当前导出内容仅包含：

- `answers`: 用户选择 + 映射编码列表（已去除括号内名称）
- `code_weights`: 编码权重汇总（同一编码重复出现会累计）
