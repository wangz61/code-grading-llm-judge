"""Enter the reference solutions through the Label Studio web UI (the same steps an annotator takes), with screenshots.

    python labelstudio/annotate_ui.py

It drives Microsoft Edge with Playwright: log in, open the labeling stream, and for each task type the
reference solution into the `ideal` text area, choose a difficulty and press Submit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
SHOTS = ROOT / "docs"
URL = os.environ.get("LS_URL", "http://127.0.0.1:8080")
EMAIL = os.environ.get("LS_EMAIL", "annotator@example.com")
PASSWORD = os.environ.get("LS_PASSWORD", "hw07-annotator")

# Reference solutions, written for this homework (task text -> (ideal, difficulty)).
IDEALS = {
    "Write a Python function to add two numbers.": (
        "def add(a, b):\n    return a + b", "easy"),
    "Write a Python function to reverse a string.": (
        "def reverse_string(s):\n    return s[::-1]", "easy"),
    "Write a Python function to check if a number is even.": (
        "def is_even(n):\n    return n % 2 == 0", "easy"),
    "Write a Python function to compute factorial.": (
        "def factorial(n):\n"
        "    if n < 0:\n"
        "        raise ValueError(\"factorial is not defined for negative numbers\")\n"
        "    result = 1\n"
        "    for i in range(2, n + 1):\n"
        "        result *= i\n"
        "    return result", "medium"),
    "Write a Python function to find the maximum of a list.": (
        "def find_max(nums):\n"
        "    if not nums:\n"
        "        raise ValueError(\"find_max() of an empty list\")\n"
        "    largest = nums[0]\n"
        "    for x in nums[1:]:\n"
        "        if x > largest:\n"
        "            largest = x\n"
        "    return largest", "easy"),
}


def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", args=["--no-proxy-server"])
        page = browser.new_page(viewport={"width": 1400, "height": 860})
        page.goto(f"{URL}/user/login/", wait_until="domcontentloaded")
        page.fill("input[name=email]", EMAIL)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url(lambda u: "login" not in u, timeout=30000)

        page.goto(f"{URL}/projects/1/data", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(SHOTS / "1-tasks-imported.png"))

        page.goto(f"{URL}/projects/1/data?labeling=1", wait_until="domcontentloaded")
        done = 0
        for _ in range(len(IDEALS) + 1):
            try:
                page.wait_for_selector("textarea", timeout=15000)
            except Exception:  # noqa: BLE001 - no more tasks in the stream
                break
            page.wait_for_timeout(800)
            task = next((t for t in IDEALS if page.get_by_text(t, exact=True).count()), None)
            if task is None:
                break
            ideal, difficulty = IDEALS[task]
            box = page.locator("textarea").first
            box.click()
            box.fill(ideal)
            box.press("End")
            page.locator(".lsf-choices").get_by_text(difficulty).first.click()
            page.wait_for_timeout(600)
            if done == 0:
                page.screenshot(path=str(SHOTS / "2-labeling.png"))
            page.get_by_test_id("bottombar-submit-button").click()
            page.wait_for_timeout(2500)
            done += 1
            print(f"submitted: {task} [{difficulty}]")

        page.goto(f"{URL}/projects/1/data", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(SHOTS / "3-all-labelled.png"))
        browser.close()
    print(f"{done} tasks submitted")
    return 0 if done == len(IDEALS) else 1


if __name__ == "__main__":
    sys.exit(main())
