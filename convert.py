"""Merge the Label Studio export (input + ideal) with the model outputs (sampled) into an eval JSONL.

    python convert.py
    python convert.py --export labelstudio/export.json --outputs data/hw0-07_inputs_model_output.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
EXPORT = ROOT / "labelstudio" / "export.json"
INPUTS = ROOT / "data" / "hw0-07_inputs.csv"
OUTPUTS = ROOT / "data" / "hw0-07_inputs_model_output.csv"
JSONL = ROOT / "data" / "samples.jsonl"
REGISTRY_COPY = ROOT / "evals_registry" / "data" / "code_grading" / "samples.jsonl"


class ConvertError(ValueError):
    pass


def read_column(path: Path, column: str) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if rows and column not in rows[0]:
        raise ConvertError(f"{path.name}: no column {column!r} (found {list(rows[0])})")
    return [r[column].strip() for r in rows]


def labelled(export: list[dict]) -> list[dict]:
    """One {input, ideal, difficulty} per task, in task order, from each task's latest submitted annotation."""
    out = []
    for task in sorted(export, key=lambda t: t["id"]):
        anns = [a for a in task.get("annotations", []) if not a.get("was_cancelled")]
        if not anns:
            raise ConvertError(f"task {task['id']} ({task['data'].get('input')!r}) has no annotation")
        ann = max(anns, key=lambda a: a.get("updated_at") or a.get("created_at") or "")
        fields = {r["from_name"]: r["value"] for r in ann["result"]}
        text = fields.get("ideal", {}).get("text", [])
        ideal = "\n".join(text).strip("\n")
        if not ideal.strip():
            raise ConvertError(f"task {task['id']} has an empty ideal")
        out.append({"input": task["data"]["input"].strip(), "ideal": ideal,
                    "difficulty": (fields.get("difficulty", {}).get("choices") or [None])[0]})
    return out


def function_name(code: str) -> str | None:
    m = re.search(r"^\s*def\s+(\w+)\s*\(", code, re.M)
    return m.group(1) if m else None


def merge(labels: list[dict], sampled: list[str], inputs: list[str] | None = None) -> list[dict]:
    if len(labels) != len(sampled):
        raise ConvertError(f"{len(labels)} labelled tasks but {len(sampled)} model outputs")
    if inputs is not None and [l["input"] for l in labels] != inputs:
        raise ConvertError("exported tasks are not the tasks in hw0-07_inputs.csv, in the same order")
    rows = []
    for i, (label, out) in enumerate(zip(labels, sampled), 1):
        ref, got = function_name(label["ideal"]), function_name(out)
        if ref and got and ref != got:
            raise ConvertError(f"row {i}: ideal defines {ref}() but sampled defines {got}(); files are misaligned")
        rows.append({"input": label["input"], "ideal": label["ideal"], "sampled": out})
    return rows


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", type=Path, default=EXPORT)
    ap.add_argument("--inputs", type=Path, default=INPUTS)
    ap.add_argument("--outputs", type=Path, default=OUTPUTS)
    ap.add_argument("--out", type=Path, default=JSONL)
    args = ap.parse_args(argv)
    try:
        labels = labelled(json.loads(args.export.read_text(encoding="utf-8")))
        rows = merge(labels, read_column(args.outputs, "sampled"), read_column(args.inputs, "input"))
    except ConvertError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    write_jsonl(rows, args.out)
    REGISTRY_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.out, REGISTRY_COPY)
    print(f"wrote {len(rows)} samples to {args.out} (copied to {REGISTRY_COPY.relative_to(ROOT)})")
    for label in labels:
        print(f"  [{label['difficulty']}] {label['input']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
