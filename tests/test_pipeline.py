import json
from pathlib import Path

import pytest
import yaml

import analyze
import convert
import functional

ROOT = Path(__file__).parent.parent


def task(tid, text, ideal, difficulty="easy", cancelled=False, updated="2026-11-11T10:00:00Z"):
    return {"id": tid, "data": {"input": text}, "annotations": [{
        "was_cancelled": cancelled, "updated_at": updated, "result": [
            {"from_name": "ideal", "to_name": "input", "type": "textarea", "value": {"text": [ideal]}},
            {"from_name": "difficulty", "to_name": "input", "type": "choices", "value": {"choices": [difficulty]}},
        ]}]}


# ---- convert ----------------------------------------------------------------------------------------------

def test_real_export_converts_to_three_key_jsonl(tmp_path):
    labels = convert.labelled(json.loads((ROOT / "labelstudio" / "export.json").read_text(encoding="utf-8")))
    rows = convert.merge(labels, convert.read_column(convert.OUTPUTS, "sampled"),
                         convert.read_column(convert.INPUTS, "input"))
    assert len(rows) == 5
    assert all(list(r) == ["input", "ideal", "sampled"] for r in rows)
    assert rows[3]["input"] == "Write a Python function to compute factorial."
    assert rows[3]["sampled"].startswith("def factorial(n):\n    result = 1")
    out = tmp_path / "s.jsonl"
    convert.write_jsonl(rows, out)
    assert [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()] == rows
    assert out.read_text(encoding="utf-8") == (ROOT / "data" / "samples.jsonl").read_text(encoding="utf-8")


def test_multiline_csv_cells_are_read_whole():
    sampled = convert.read_column(convert.OUTPUTS, "sampled")
    assert len(sampled) == 5
    assert sampled[2] == "def is_even(n):\n    if n % 2 == 0:\n        return True\n    else:\n        return False"


def test_latest_annotation_wins_and_cancelled_ignored():
    t = task(1, "Add.", "def add(a, b):\n    return a - b\n", updated="2026-11-10T00:00:00Z")
    t["annotations"].append(task(1, "Add.", "def add(a, b):\n    return a + b\n")["annotations"][0])
    t["annotations"].append(task(1, "Add.", "junk", cancelled=True, updated="2026-11-12T00:00:00Z")["annotations"][0])
    assert convert.labelled([t]) == [{"input": "Add.", "ideal": "def add(a, b):\n    return a + b", "difficulty": "easy"}]


def test_tasks_are_ordered_by_id():
    out = convert.labelled([task(2, "B", "def b(): pass"), task(1, "A", "def a(): pass")])
    assert [o["input"] for o in out] == ["A", "B"]


@pytest.mark.parametrize("tasks, sampled, inputs, message", [
    ([{"id": 1, "data": {"input": "A"}, "annotations": []}], ["x"], None, "no annotation"),
    ([task(1, "A", "  \n")], ["x"], None, "empty ideal"),
    ([task(1, "A", "def a(): pass")], ["x", "y"], None, "1 labelled tasks but 2 model outputs"),
    ([task(1, "A", "def a(): pass")], ["def a(): pass"], ["B"], "not the tasks"),
    ([task(1, "A", "def add(a, b): return a + b")], ["def find_max(x): return x"], None, "misaligned"),
], ids=["no-annotation", "empty-ideal", "count-mismatch", "wrong-tasks", "misaligned"])
def test_merge_errors(tasks, sampled, inputs, message):
    with pytest.raises(convert.ConvertError, match=message):
        convert.merge(convert.labelled(tasks), sampled, inputs)


# ---- functional -------------------------------------------------------------------------------------------

def test_functional_check_matches_known_bugs():
    rows = {r["function"]: r for r in functional.check_file(ROOT / "data" / "samples.jsonl")}
    assert all(r["ideal_passed"] == r["ideal_total"] for r in rows.values())
    assert rows["add"]["sampled_passed"] == rows["add"]["sampled_total"]
    assert rows["factorial"]["sampled_passed"] == 2      # only 0! and 1! are right (off-by-one)
    assert rows["find_max"]["sampled_passed"] == 1       # returns the minimum; right only for [7]
    assert "find_max([3, 1, 2]) expected 3, got 1" in rows["find_max"]["sampled_failures"]


def test_functional_check_handles_broken_code():
    assert functional.check("def add(a, b) return a + b").failures[0].startswith("SyntaxError")
    assert functional.check("x = 1").failures == ["no known function defined"]
    hang = functional.check("def add(a, b):\n    while True: pass", timeout=2)
    assert hang.failures == ["timed out"]


# ---- analyze ----------------------------------------------------------------------------------------------

def write_record(path, choices):
    lines = [{"spec": {"eval_name": "code-grading.dev.v0"}}]
    for i, c in enumerate(choices):
        sid = f"code-grading.dev.v0.{i}"
        lines.append({"sample_id": sid, "type": "sampling", "data": {"sampled": [f"reasoning {i}\n{c}"]}})
        lines.append({"sample_id": sid, "type": "metrics",
                      "data": {"choice": c, "score": None if c == "__invalid__" else int(c)}})
    lines.append({"final_report": {"score": 0}})
    path.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")


def test_read_record(tmp_path):
    write_record(tmp_path / "run_1.jsonl", ["5", "3", "__invalid__"])
    js = analyze.read_record(tmp_path / "run_1.jsonl")
    assert [(j.index, j.choice, j.score) for j in js] == [(0, "5", 5), (1, "3", 3), (2, "__invalid__", None)]
    assert js[1].reasoning == "reasoning 1\n3"


def test_summary_statistics(tmp_path):
    for i, choices in enumerate([["5", "1", "3"], ["5", "3", "3"]], 1):
        write_record(tmp_path / f"run_{i}.jsonl", choices)
    s = analyze.summarise(analyze.load_runs(tmp_path))
    assert s.sample_means == [5.0, 2.0, 3.0]
    assert s.run_means == [3.0, pytest.approx(11 / 3)]
    assert s.mean == pytest.approx(10 / 3)
    assert s.between_variance == pytest.approx(7 / 3)          # variance of 5, 2, 3
    assert s.judge_variance == pytest.approx((0 + 2 + 0) / 3)  # only sample 1 moved (1 vs 3)
    assert s.stderr == pytest.approx((7 / 9) ** 0.5)
    lo, hi = s.t_interval
    assert (lo + hi) / 2 == pytest.approx(s.mean) and hi - lo == pytest.approx(2 * 4.303 * s.stderr)
    blo, bhi = s.bootstrap_interval()
    assert 2.0 <= blo <= s.mean <= bhi <= 5.0


def test_invalid_answers_count_as_lowest_grade(tmp_path):
    write_record(tmp_path / "run_1.jsonl", ["5", "__invalid__"])
    s = analyze.summarise(analyze.load_runs(tmp_path))
    assert s.invalid == 1 and s.per_sample == [[5.0], [1.0]]


def test_t95_table():
    assert analyze.t95(4) == 2.776
    assert analyze.t95(12) == 2.228   # falls back to the nearest smaller tabulated df


# ---- eval config ------------------------------------------------------------------------------------------

def test_eval_config():
    evals_cfg = yaml.safe_load((ROOT / "evals_registry" / "evals" / "code-grading.yaml").read_text(encoding="utf-8"))
    args = evals_cfg["code-grading.dev.v0"]["args"]
    assert evals_cfg["code-grading"]["id"] == "code-grading.dev.v0"
    assert args["eval_type"] == "cot_classify" and args["eval_kwargs"]["temperature"] == 0
    assert (ROOT / "evals_registry" / "data" / args["samples_jsonl"]).exists()

    spec = yaml.safe_load((ROOT / "evals_registry" / "modelgraded" / "code_grading.yaml").read_text(encoding="utf-8"))
    spec = spec[args["modelgraded_spec"]]
    assert spec["choice_strings"] == "12345"
    assert spec["choice_scores"] == {str(i): i for i in range(1, 6)}
    assert spec["input_outputs"] == {"input": "sampled"}      # graded outputs come from the JSONL, not a new model call
    for placeholder in ("{input}", "{ideal}", "{sampled}"):
        assert placeholder in spec["prompt"]
    for line in ("5 - fully correct", "4 - correct, minor issues", "3 - partially correct",
                 "2 - major issues", "1 - incorrect"):
        assert line in spec["prompt"]


def test_usage_patch_ignores_nested_details():
    import evals.cli.oaieval as cli

    import evals_ext  # noqa: F401 - importing applies the patch

    class Event:
        def __init__(self, usage):
            self.data = {"usage": usage}

    class Recorder:
        def get_events(self, kind):
            return [Event({"prompt_tokens": 10, "completion_tokens": 5, "completion_tokens_details": object()}),
                    Event({"prompt_tokens": 7, "completion_tokens": 3, "prompt_tokens_details": None})]

    result = {}
    cli.add_token_usage_to_result(result, Recorder())
    assert result == {"usage_prompt_tokens": 17, "usage_completion_tokens": 8}
