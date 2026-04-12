#!/usr/bin/env python3
"""
Backend test agent — runs pytest inside Docker, analyses failures with local Ollama,
writes a fix report. Loops until all tests pass or max_rounds exhausted.
"""

import subprocess, json, time, re, urllib.request, sys, os
from datetime import datetime

OLLAMA_URL   = "http://localhost:11434/api/chat"
MODEL        = "qwen2.5:3b"
PROJECT_DIR  = "/root/projects/med-ai-project"
REPORT_FILE  = f"{PROJECT_DIR}/scripts/report_backend.json"
MAX_ROUNDS   = 5


def log(msg):
    print(f"[backend-agent] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def ollama(prompt, context=""):
    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": MODEL, "messages": messages, "stream": False,
        "options": {"num_predict": 1024, "temperature": 0.2}
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["message"]["content"]
    except Exception as e:
        return f"[ollama error: {e}]"


def run_pytest():
    cmd = [
        "docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml",
        "exec", "-T", "iatronix-backend",
        "python", "-m", "pytest", "tests/", "-x", "-q", "--tb=short", "--no-header"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=PROJECT_DIR, timeout=120)
    return result.stdout + result.stderr, result.returncode


def check_api_health():
    import urllib.request as ur
    results = {}
    endpoints = [
        ("health",    "http://localhost:8200/api/v1/health"),
        ("docs",      "http://localhost:8200/docs"),
    ]
    for name, url in endpoints:
        try:
            with ur.urlopen(url, timeout=5) as r:
                results[name] = r.status
        except Exception as e:
            results[name] = str(e)
    return results


def run():
    log("Starting backend test agent")
    report = {"rounds": [], "final_status": "unknown", "fixes": []}

    for rnd in range(1, MAX_ROUNDS + 1):
        log(f"Round {rnd}/{MAX_ROUNDS} — running pytest")
        output, rc = run_pytest()
        health = check_api_health()
        log(f"  pytest exit={rc}, health={health}")

        round_result = {
            "round": rnd,
            "pytest_exit": rc,
            "health": health,
            "output_tail": output[-3000:],
            "fixes_suggested": [],
        }

        if rc == 0:
            log("  All tests PASS")
            round_result["status"] = "pass"
            report["rounds"].append(round_result)
            report["final_status"] = "all_pass"
            break

        # Analyse failures with Ollama
        log(f"  Tests failed — asking Ollama to diagnose")
        analysis = ollama(
            f"These pytest tests failed in a FastAPI medical AI backend.\n\n"
            f"OUTPUT:\n{output[-2500:]}\n\n"
            f"List the top 3 most important fixes needed. For each fix give:\n"
            f"1. File path (relative to backend/)\n"
            f"2. What the problem is\n"
            f"3. The exact code change needed\n"
            f"Be specific and concise.",
            context="You are a Python/FastAPI expert analyzing test failures."
        )
        log(f"  Ollama analysis done ({len(analysis)} chars)")
        round_result["fixes_suggested"] = analysis
        round_result["status"] = "fail"
        report["rounds"].append(round_result)
        report["fixes"].append({"round": rnd, "analysis": analysis})

        log(f"  Fixes needed:\n{analysis[:500]}")
        time.sleep(5)

    report["final_status"] = report.get("final_status", "incomplete")
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    log(f"Report written to {REPORT_FILE}")
    log(f"Final status: {report['final_status']}")
    return report


if __name__ == "__main__":
    run()
