"""Run the OpenAI Evals model-graded eval several times and keep every record file.

    python run_eval.py                    # code-grading (judge at temperature 0), 5 runs
    python run_eval.py --eval code-grading-t1 --runs 5
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
REGISTRY = ROOT / "evals_registry"


def oaieval() -> str:
    exe = shutil.which("oaieval", path=str(Path(sys.executable).parent)) or shutil.which("oaieval")
    if not exe:
        raise SystemExit("oaieval not found: pip install evals")
    return exe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="code-grading")
    ap.add_argument("--judge", default="gpt-4.1-chat", help="completion function used as the judge")
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("set OPENAI_API_KEY first")

    out = ROOT / "results" / "runs" / args.eval
    out.mkdir(parents=True, exist_ok=True)
    for i in range(1, args.runs + 1):
        record = out / f"run_{i}.jsonl"
        record.unlink(missing_ok=True)
        # blobfile (used by Evals to write records) rejects Windows drive paths, so pass paths relative to ROOT.
        cmd = [oaieval(), args.judge, args.eval, "--registry_path", REGISTRY.relative_to(ROOT).as_posix(),
               "--record_path", record.relative_to(ROOT).as_posix(), "--seed", str(i)]
        print(f"[{i}/{args.runs}] " + " ".join(Path(c).name if c == cmd[0] else c for c in cmd), flush=True)
        env = {**os.environ, "PYTHONPATH": str(ROOT)}  # so the registry can import evals_ext
        proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (out / f"run_{i}.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            print(proc.stdout[-2000:] + proc.stderr[-4000:], file=sys.stderr)
            return proc.returncode
        report = [l for l in (proc.stdout + proc.stderr).splitlines() if "Final report" in l or l.strip().startswith(("score", "counts/"))]
        print("    " + " | ".join(l.split("]")[-1].strip() for l in report[-8:]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
