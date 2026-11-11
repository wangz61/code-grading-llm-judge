"""Summarise OpenAI Evals record files: mean score, variance and uncertainty.

    python analyze.py                       # every eval under results/runs/
    python analyze.py results/runs/code-grading
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent
# Two-sided 95% critical values of Student's t, by degrees of freedom.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
       15: 2.131, 20: 2.086, 30: 2.042}


def t95(df: int) -> float:
    return T95.get(df) or T95[max(k for k in T95 if k <= df)] if df >= 1 else float("nan")


@dataclass
class Judgement:
    index: int          # position of the sample in samples.jsonl
    choice: str         # "1".."5" or "__invalid__"
    score: float | None
    reasoning: str      # the judge's full answer


def read_record(path: Path) -> list[Judgement]:
    """Parse one oaieval record file. Sample ids look like '<eval>.<split>.<version>.<index>'."""
    metrics, answers = {}, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        sid = event.get("sample_id")
        if sid is None:
            continue
        idx = int(sid.rsplit(".", 1)[1])
        if event.get("type") == "metrics":
            metrics[idx] = event["data"]
        elif event.get("type") == "sampling":
            sampled = event["data"].get("sampled")
            answers[idx] = sampled[0] if isinstance(sampled, list) else str(sampled)
    return [Judgement(i, str(m["choice"]), m.get("score"), answers.get(i, "")) for i, m in sorted(metrics.items())]


@dataclass
class Summary:
    runs: int
    samples: int
    run_means: list[float]
    per_sample: list[list[float]]   # per_sample[i] = scores of sample i across runs
    invalid: int

    @property
    def sample_means(self) -> list[float]:
        return [st.mean(s) for s in self.per_sample]

    @property
    def mean(self) -> float:
        return st.mean(self.sample_means)

    @property
    def between_variance(self) -> float:
        """Variance of the per-sample mean scores: how much the test cases differ from each other."""
        return st.variance(self.sample_means) if self.samples > 1 else 0.0

    @property
    def judge_variance(self) -> float:
        """Average within-sample variance across runs: the judge's own randomness."""
        return st.mean(st.variance(s) for s in self.per_sample) if self.runs > 1 else 0.0

    @property
    def stderr(self) -> float:
        return (self.between_variance / self.samples) ** 0.5

    @property
    def t_interval(self) -> tuple[float, float]:
        half = t95(self.samples - 1) * self.stderr
        return self.mean - half, self.mean + half

    def bootstrap_interval(self, reps: int = 10000, seed: int = 0) -> tuple[float, float]:
        rng = random.Random(seed)
        means = self.sample_means
        boots = sorted(st.mean(rng.choices(means, k=len(means))) for _ in range(reps))
        return boots[int(0.025 * reps)], boots[int(0.975 * reps) - 1]


def summarise(runs: list[list[Judgement]]) -> Summary:
    n = len(runs[0])
    if any(len(r) != n for r in runs):
        raise ValueError("runs graded different numbers of samples")
    invalid = sum(j.score is None for r in runs for j in r)
    # An invalid answer scores as 1 (the lowest grade), so a broken judge can't inflate the mean.
    per_sample = [[float(r[i].score) if r[i].score is not None else 1.0 for r in runs] for i in range(n)]
    run_means = [st.mean(float(j.score) if j.score is not None else 1.0 for j in r) for r in runs]
    return Summary(len(runs), n, run_means, per_sample, invalid)


def load_runs(folder: Path) -> list[list[Judgement]]:
    files = sorted(folder.glob("run_*.jsonl"), key=lambda p: int(p.stem.split("_")[1]))
    return [read_record(p) for p in files]


def report(name: str, s: Summary, labels: list[str] | None = None) -> str:
    labels = labels or [f"sample {i}" for i in range(s.samples)]
    width = max(len(l) for l in labels)
    lines = [f"== {name}: {s.runs} runs x {s.samples} samples", "",
             f"{'sample':<{width}}  " + " ".join(f"r{i + 1}" for i in range(s.runs)) + "   mean    std"]
    for label, scores in zip(labels, s.per_sample):
        sd = st.stdev(scores) if len(scores) > 1 else 0.0
        lines.append(f"{label:<{width}}  " + " ".join(f"{x:>2.0f}" for x in scores) + f"   {st.mean(scores):.2f}   {sd:.2f}")
    lo, hi = s.t_interval
    blo, bhi = s.bootstrap_interval()
    lines += [
        "",
        "Run means: " + ", ".join(f"{m:.2f}" for m in s.run_means)
        + (f"   (std across runs {st.stdev(s.run_means):.3f})" if s.runs > 1 else ""),
        f"Mean score:                      {s.mean:.2f} / 5",
        f"Variance between samples:        {s.between_variance:.2f}   (std {s.between_variance ** 0.5:.2f})",
        f"Judge variance within a sample:  {s.judge_variance:.3f}",
        f"Standard error of the mean:      {s.stderr:.2f}   (n = {s.samples} samples)",
        f"95% CI, t distribution:          [{lo:.2f}, {hi:.2f}]",
        f"95% CI, bootstrap over samples:  [{blo:.2f}, {bhi:.2f}]",
        f"Invalid judge answers:           {s.invalid}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    folders = [Path(a) for a in argv] or sorted(p for p in (ROOT / "results" / "runs").iterdir() if p.is_dir())
    samples = [json.loads(l) for l in (ROOT / "data" / "samples.jsonl").read_text(encoding="utf-8").splitlines() if l]
    labels = [s["input"].replace("Write a Python function to ", "").rstrip(".") for s in samples]
    texts = []
    for folder in folders:
        runs = load_runs(folder)
        if not runs:
            continue
        s = summarise(runs)
        texts.append(report(folder.name, s, labels))
        summary = {"eval": folder.name, "runs": s.runs, "samples": s.samples, "mean": s.mean,
                   "between_variance": s.between_variance, "judge_variance": s.judge_variance,
                   "stderr": s.stderr, "t_interval": s.t_interval, "bootstrap_interval": s.bootstrap_interval(),
                   "run_means": s.run_means, "per_sample": s.per_sample, "invalid": s.invalid}
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    text = "\n\n".join(texts)
    print(text)
    (ROOT / "results" / "analysis.txt").write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
