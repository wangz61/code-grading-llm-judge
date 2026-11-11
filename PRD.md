# PRD · Homework 0-7 代码评分系统（LLM-as-a-Judge）

## 1. 目标
用 Label Studio 为 5 道编程题标注参考答案（ideal），与已有模型输出（sampled）合并成 JSONL，再用 OpenAI Evals 的 model-graded 方式让 LLM 按 1–5 分评分，最后解读结果：平均分、方差、不确定性。

## 2. 需求

| ID | 优先级 | 需求 |
| --- | --- | --- |
| L-1 | P0 | 安装并启动 Label Studio，创建项目，导入 `hw0-07_inputs.csv` 的 5 道题 |
| L-2 | P0 | 自定义标注界面：显示题目；`ideal` 多行文本框填写参考答案（必填）；`difficulty` 单选 easy / medium / hard |
| L-3 | P0 | 在 Label Studio 界面中完成 5 条标注，导出为 JSON 文件 |
| C-1 | P0 | `convert.py`：读取 Label Studio 导出 JSON 与 `hw0-07_inputs_model_output.csv`，按顺序合并 |
| C-2 | P0 | 输出 `data/samples.jsonl`，每行一个对象，只有 `input`、`ideal`、`sampled` 三个键 |
| C-3 | P1 | 合并前校验：两边条数一致、题目文本与导出的 input 一致、每条都有 ideal |
| E-1 | P0 | 评分提示词：5 fully correct、4 correct with minor issues、3 partially correct、2 major issues、1 incorrect；先推理再给分 |
| E-2 | P0 | OpenAI Evals 配置：eval 注册 YAML 与 modelgraded spec YAML（`cot_classify`，choice_strings 1–5，choice_scores 1–5），用 `oaieval` 运行 |
| E-3 | P1 | 不确定性：同一配置重复运行 5 次，统计每题得分的均值和标准差、总体平均分、各题之间的方差、标准误和 95% 置信区间（t 分布 + bootstrap）、每次运行平均分的波动 |
| E-4 | P1 | 规则对照：用单元测试真实执行 sampled 和 ideal 代码，得到通过率，与评委分数对照 |
| Q-1 | P1 | pytest：转换、校验、统计、单元测试执行器 |
| Q-2 | P0 | 提交 Word / PDF：代码、标注界面截图、导出文件、JSONL、评测运行截图与结果解读 |

## 3. 设计

```
labelstudio/label_config.xml   标注界面
labelstudio/setup_project.py   通过 REST API 建项目、导入题目、导出 JSON
labelstudio/annotate_ui.py     用浏览器在 Label Studio 界面里逐条填写并提交，同时截图
labelstudio/export.json        Label Studio 导出文件
convert.py                     导出 JSON + model_output CSV -> data/samples.jsonl
evals_registry/                OpenAI Evals 注册目录：evals/、modelgraded/、data/
run_eval.py                    运行 oaieval N 次，保存记录
analyze.py                     读取记录：均值、方差、标准误、置信区间、每题明细
functional.py                  执行代码的单元测试对照
```

- 评委模型：`gpt-4.1`（课件示例模型）。`sampled` 已经存在，Evals 会跳过生成，只调用评委。
- 按位置合并：两个 CSV 都是 5 行，顺序相同；合并前检查函数名与题目对应。
- 参考答案由 Claude 编写，并在 Label Studio 界面中逐条填写提交。用户可以在 Label Studio 中复查或修改，再重新导出。

## 4. 验收
- Label Studio 中 5 条任务都已标注，导出的 JSON 可被 `convert.py` 读取。
- `samples.jsonl` 共 5 行，键严格为 input / ideal / sampled。
- `oaieval` 运行成功，5 次运行的记录都保存在 `results/`；报告给出平均分、方差和置信区间。
- 评委分数与单元测试结果方向一致：factorial 和 find_max 是错误实现，应得低分。
- pytest 全部通过。

## 5. 里程碑
- P0：Label Studio 标注与导出、JSONL 转换、评分提示词与 Evals 配置、运行
- P1：重复运行与不确定性分析、单元测试对照、测试
- P2：提交文档、GitHub

## 6. 完成情况

| ID | 状态 | 说明 |
| --- | --- | --- |
| L-1 – L-3 | ✅ | Label Studio 1.23.2；项目 + 自定义界面；5 条标注在界面中提交；导出 `labelstudio/export.json` |
| C-1 – C-3 | ✅ | `convert.py` → `data/samples.jsonl`，5 行，键为 input / ideal / sampled；校验条数、题目、函数名 |
| E-1 – E-2 | ✅ | `cot_classify` 评分提示词；`oaieval gpt-4.1-chat code-grading` 运行成功 |
| E-3 | ✅ | 温度 0 与 1 各 5 次：平均分 3.44 / 3.48，标准误 0.78，bootstrap 95% CI [2.08, 4.80] |
| E-4 | ✅ | 单元测试：3/5 全部通过；factorial 2/5、find_max 1/4，与评委低分一致 |
| Q-1 | ✅ | pytest 17 项通过 |
| Q-2 | ✅ | `submission/hw0-7.docx` 与 `.pdf` |
