"""Create the Label Studio project, import the tasks, and export the annotations, via the REST API.

    python labelstudio/setup_project.py create     # project + labeling interface + import hw0-07_inputs.csv
    python labelstudio/setup_project.py export     # write labelstudio/export.json

Reads LS_URL (default http://localhost:8080) and LS_TOKEN from the environment or labelstudio/.env.local.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).parent
ROOT = HERE.parent
TITLE = "hw0-7 Code Reference Solutions"


def settings() -> tuple[str, dict]:
    env = {}
    local = HERE / ".env.local"
    if local.exists():
        env = dict(line.split("=", 1) for line in local.read_text().split() if "=" in line)
    url = os.environ.get("LS_URL", env.get("LS_URL", "http://localhost:8080")).rstrip("/")
    token = os.environ.get("LS_TOKEN", env.get("LS_TOKEN"))
    if not token:
        raise SystemExit("set LS_TOKEN")
    return url, {"Authorization": f"Token {token}"}


def find_project(url, headers) -> dict | None:
    resp = requests.get(f"{url}/api/projects", headers=headers, params={"title": TITLE}, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    projects = body["results"] if isinstance(body, dict) else body
    return next((p for p in projects if p["title"] == TITLE), None)


def create() -> int:
    url, headers = settings()
    if (project := find_project(url, headers)) is not None:
        print(f"project {project['id']} already exists: {url}/projects/{project['id']}")
        return 0
    config = (HERE / "label_config.xml").read_text(encoding="utf-8")
    resp = requests.post(f"{url}/api/projects", headers=headers, timeout=30, json={
        "title": TITLE,
        "description": "Write a correct reference solution (ideal) for each programming task.",
        "label_config": config,
        "show_skip_button": False,
    })
    resp.raise_for_status()
    project = resp.json()
    with open(ROOT / "data" / "hw0-07_inputs.csv", "rb") as f:
        imp = requests.post(f"{url}/api/projects/{project['id']}/import", headers=headers, timeout=60,
                            files={"file": ("hw0-07_inputs.csv", f, "text/csv")})
    imp.raise_for_status()
    print(f"created project {project['id']} with {imp.json().get('task_count')} tasks: {url}/projects/{project['id']}")
    return 0


def export(out: Path = HERE / "export.json") -> int:
    url, headers = settings()
    project = find_project(url, headers)
    if project is None:
        raise SystemExit("project not found; run create first")
    resp = requests.get(f"{url}/api/projects/{project['id']}/export", headers=headers, timeout=60,
                        params={"exportType": "JSON", "download_all_tasks": "true"})
    resp.raise_for_status()
    tasks = resp.json()
    out.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
    done = sum(bool(t.get("annotations")) for t in tasks)
    print(f"exported {len(tasks)} tasks ({done} annotated) to {out}")
    return 0 if done == len(tasks) else 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    sys.exit({"create": create, "export": export}[action]())
