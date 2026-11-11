"""Rule-based cross-check: execute each solution against unit tests, so the judge's grades can be compared with behaviour."""
from __future__ import annotations

import json
import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent

# Test cases by function name: (args, expected). They cover typical inputs and the edge cases each task implies.
TESTS: dict[str, list[tuple[tuple, object]]] = {
    "add": [((2, 3), 5), ((-1, 1), 0), ((0, 0), 0), ((0.5, 0.25), 0.75)],
    "reverse_string": [(("abc",), "cba"), (("",), ""), (("a",), "a"), (("racecar",), "racecar"), (("ab cd",), "dc ba")],
    "is_even": [((4,), True), ((7,), False), ((0,), True), ((-2,), True), ((-3,), False)],
    "factorial": [((0,), 1), ((1,), 1), ((2,), 2), ((5,), 120), ((10,), 3628800)],
    "find_max": [(([3, 1, 2],), 3), (([-5, -2, -9],), -2), (([7],), 7), (([1, 9, 9, 4],), 9)],
}


@dataclass
class Result:
    function: str | None
    passed: int
    total: int
    failures: list[str]

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def _run(code: str, out) -> None:
    namespace: dict = {}
    try:
        exec(compile(code, "<solution>", "exec"), namespace)
    except Exception as err:  # noqa: BLE001 - any failure to load the code is a result
        out.put(("load", repr(err)))
        return
    funcs = [k for k, v in namespace.items() if k in TESTS and callable(v)]
    if not funcs:
        out.put(("load", "no known function defined"))
        return
    name = funcs[0]
    results = []
    for args, expected in TESTS[name]:
        try:
            got = namespace[name](*args)
            results.append((", ".join(map(repr, args)), repr(expected), repr(got), got == expected))
        except Exception as err:  # noqa: BLE001
            results.append((", ".join(map(repr, args)), repr(expected), repr(err), False))
    out.put((name, results))


def check(code: str, timeout: float = 5.0) -> Result:
    """Run `code` in a separate process (so a hang or crash cannot take the caller down) and score it."""
    queue = mp.Queue()
    proc = mp.Process(target=_run, args=(code, queue))
    proc.start()
    proc.join(timeout)
    if proc.is_alive():
        proc.terminate()
        return Result(None, 0, 1, ["timed out"])
    name, payload = queue.get()
    if name == "load":
        return Result(None, 0, 1, [payload])
    failures = [f"{name}({a}) expected {e}, got {g}"
                for a, e, g, ok in payload if not ok]
    return Result(name, sum(ok for *_, ok in payload), len(payload), failures)


def check_file(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    for row in rows:
        s, i = check(row["sampled"]), check(row["ideal"])
        out.append({"input": row["input"], "function": s.function or i.function,
                    "sampled_passed": s.passed, "sampled_total": s.total, "sampled_failures": s.failures,
                    "ideal_passed": i.passed, "ideal_total": i.total})
    return out


if __name__ == "__main__":
    for r in check_file(ROOT / "data" / "samples.jsonl"):
        print(f"{r['function']:<15} sampled {r['sampled_passed']}/{r['sampled_total']}   "
              f"ideal {r['ideal_passed']}/{r['ideal_total']}   {'; '.join(r['sampled_failures'])}")
