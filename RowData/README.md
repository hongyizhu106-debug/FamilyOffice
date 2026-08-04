# RowData

这是一个从“问卷作答”到“诊断报告生成”的本地流水线项目。核心流程是：

- Step1：问卷与输入数据
- Step2：指标计算与评分逻辑
- Step3：诊断方法论与规则抽取
- Step4：HTML/PDF 报告生成与校验

## 目录结构

- [MainController/](MainController/)：本地 Web 启动器
- [Step1/](Step1/)：问卷、题库与答卷输出
- [Step2/](Step2/)：指标计算与引擎逻辑
- [Step3/](Step3/)：PDF 抽取与方法论索引
- [Step4/](Step4/)：报告模板与生成器

## 快速开始

### 控制台问卷

在项目根目录运行：

```powershell
D:/RowData/Step1/Env/Scripts/python.exe Step1/Constructor/Survey_cli.py
```

指定题库与输出目录：

```powershell
D:/RowData/Step1/Env/Scripts/python.exe Step1/Constructor/Survey_cli.py D:/RowData/Step1/Data/Questions.json D:/RowData/Step1/Rubbish
```

答卷默认输出到 [Step1/Rubbish/](Step1/Rubbish/)。

### 网页版问卷

推荐双击运行 [MainController/Start_Web.bat](MainController/Start_Web.bat)，或手动启动：

```powershell
D:/RowData/Step1/Env/Scripts/python.exe Step1/Constructor/Web_survey_app.py
```

浏览器访问：`http://127.0.0.1:5000/`。

### 报告生成

使用 Step4 生成 HTML（可进一步导出 PDF）：

```powershell
D:/RowData/Step1/Env/Scripts/python.exe -m Step4.report_generator --input <response.json> --out-dir <out_dir>
```

校验报告：

```powershell
D:/RowData/Step1/Env/Scripts/python.exe -m Step4.validate_report <report.html>
```

## 说明文档

- Step1 运行与题库：见 [Step1/STEP1_SUMMARY.md](Step1/STEP1_SUMMARY.md)
- Step3 方法论索引：见 [Step3/STEP3_UNDERSTANDING.md](Step3/STEP3_UNDERSTANDING.md)
