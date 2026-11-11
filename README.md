# Code Grading with LLM-as-a-Judge

Homework 0-7. Model-written Python functions are graded from 1 to 5 against human reference solutions, using OpenAI Evals with a model-graded (LLM-as-a-judge) eval. The pipeline:

1. **Label.** Reference solutions for the five tasks in `hw0-07_inputs.csv` are entered in **Label Studio** through a custom labeling interface and exported as JSON.
2. **Convert.** The export is merged with the model outputs in `hw0-07_inputs_model_output.csv` into `data/samples.jsonl`, with one `{"input", "ideal", "sampled"}` object per line.
3. **Evaluate.** `oaieval` runs a `ModelBasedClassify` eval in which `gpt-4.1` grades each `sampled` solution with the 5-point rubric.
4. **Interpret.** The eval is repeated 5 times. The analysis reports the mean score, variance, standard error and confidence intervals, and compares the grades with unit tests that actually run the code.

The spec is in [PRD.md](PRD.md).

## Results

5 runs, with the judge at temperature 0 (`results/analysis.txt`):

| Task | Judge scores, runs 1–5 | Mean | Unit tests passed by `sampled` | Why |
| --- | --- | --- | --- | --- |
| add two numbers | 5 5 5 5 5 | 5.0 | 4/4 | correct |
| reverse a string | 5 5 5 5 5 | 5.0 | 5/5 | correct, a different approach from the reference |
| check if a number is even | 4 4 4 4 4 | 4.0 | 5/5 | correct, but uses a verbose `if/else` around a boolean |
| compute factorial | 2 2 2 2 2 | 2.0 | 2/5 | `range(1, n)` is off by one, so only 0! and 1! are right |
| find the maximum of a list | 1 1 1 1 2 | 1.2 | 1/4 | `sorted(nums)[0]` returns the minimum |

| Statistic | Judge at temperature 0 | Judge at temperature 1 |
| --- | --- | --- |
| Mean score | **3.44 / 5** | 3.48 / 5 |
| Variance between tasks (std) | 3.07 (1.75) | 2.85 (1.69) |
| Judge variance within a task | 0.040 | 0.060 |
| Std of the mean across runs | 0.09 | 0.11 |
| Standard error of the mean (n = 5 tasks) | 0.78 | 0.76 |
| 95% CI, t distribution | [1.27, 5.61], i.e. up to the 5.0 ceiling | [1.38, 5.58] |
| 95% CI, bootstrap over tasks | [2.08, 4.80] | [2.16, 4.80] |

**Reading the numbers**

- **The mean hides two groups.** Three solutions are correct, scoring 4–5 and passing every test. Two are wrong, scoring 1–2. The 3.44 average describes neither group, which is why the variance between tasks is large.
- **Most of the uncertainty comes from having only 5 test cases, not from the judge.** Repeating the judge moves the mean by only about 0.1. The standard error is 0.78, which gives a 95% interval about 3 points wide. Narrowing it takes more tasks, not more runs.
- **Temperature 0 is not fully deterministic.**
  - find_max received a 2 in one of the 5 runs.
  - In an extra run, the one in the screenshot, is_even received a 5 instead of 4.
  - Both are boundary cases:
    - `sorted(nums)[0]` is one index away from correct (`[-1]`). The judge sometimes calls it a related approach with a bug (2) instead of computing something else (1).
    - Whether a verbose `if/else` is a "minor issue" is a judgement call.
- **The judge agrees with the tests.** Solutions that pass all tests get 4–5, and those that fail most tests get 1–2. Rule-based pass rate: 3/5 solutions are fully correct.

## Run

Label Studio and Evals have conflicting dependencies, so each gets its own virtual environment.

```bash
# Label Studio (labeling)
python -m venv .venv-ls && .venv-ls/Scripts/pip install -r requirements-labelstudio.txt
label-studio start --port 8080 --internal-host 127.0.0.1
python labelstudio/setup_project.py create     # project, labeling interface, import tasks (needs LS_TOKEN)
python labelstudio/annotate_ui.py              # optional: fills the UI automatically (Playwright + Edge)
python labelstudio/setup_project.py export     # -> labelstudio/export.json

# Evals (convert, grade, analyse)
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
python convert.py                              # -> data/samples.jsonl
export OPENAI_API_KEY=...
python run_eval.py --runs 5                    # oaieval gpt-4.1-chat code-grading, 5 times
python run_eval.py --eval code-grading-t1 --runs 5
python analyze.py
python functional.py
```

A single run without the wrapper:

```bash
PYTHONPATH=. oaieval gpt-4.1-chat code-grading --registry_path evals_registry --record_path results/run.jsonl
```

## Eval config

| File | Purpose |
| --- | --- |
| `evals_registry/evals/code-grading.yaml` | Registers the eval: `ModelBasedClassify`, `cot_classify`, judge at temperature 0. `code-grading-t1` is the same eval with the judge at temperature 1 |
| `evals_registry/modelgraded/code_grading.yaml` | The grading prompt and rubric. `choice_strings: "12345"` with matching `choice_scores`, and `input_outputs: {input: sampled}` |
| `evals_registry/completion_fns/gpt-4.1-chat.yaml` | The judge `gpt-4.1`, routed to the chat endpoint |
| `evals_ext.py` | Two compatibility fixes for Evals 3.0 (below) |

`input_outputs: {input: sampled}` tells Evals that each sample already contains its output. The model outputs are therefore graded as given, and no new completions are generated.

The eval runs on Windows with three fixes:
- `evals_ext.py` routes `gpt-4.1` to the chat endpoint. Evals sends model names it doesn't know to the legacy completions endpoint.
- `evals_ext.py` replaces Evals' token-usage totals, which crash on the nested `*_details` fields in newer OpenAI SDK responses.
- `run_eval.py` passes record paths relative to the project. `blobfile`, which Evals uses to write records, rejects Windows drive paths.

## Labeling

- The labeling interface is in `labelstudio/label_config.xml`. It shows the task, a required multi-line `ideal` text area for the reference solution, and a single-choice `difficulty` (easy / medium / hard).
- I wrote the reference solutions and entered them through the Label Studio UI with `annotate_ui.py`. Screenshots are in `docs/`.
- To review or change them, open the project, edit the annotations, and export and convert again.

## Test

```bash
pytest
```

The 17 tests cover:
- the conversion, including a misaligned or incomplete export;
- the unit-test runner, including syntax errors and timeouts;
- the statistics;
- the eval config;
- the token-usage fix.

## Layout

```
labelstudio/    labeling interface, project setup/export, UI annotation script, export.json
data/           the two input CSVs and samples.jsonl
evals_registry/ OpenAI Evals registry: evals/, modelgraded/, completion_fns/, data/
convert.py      export + model outputs -> samples.jsonl
run_eval.py     runs oaieval N times
analyze.py      mean, variance, standard error, confidence intervals
functional.py   unit tests that execute each solution
evals_ext.py    Evals compatibility fixes
results/        record files from every run, and analysis.txt
docs/           screenshots
```
