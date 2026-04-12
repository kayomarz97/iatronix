#!/usr/bin/env python3
"""
Frontend test agent — runs TypeScript type-check and lint inside Docker,
checks for dead features (no backend route), analyses with Ollama.
"""

import subprocess, json, time, re, urllib.request, sys, os, glob
from datetime import datetime

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen2.5:3b"
PROJECT_DIR = "/root/projects/med-ai-project"
REPORT_FILE = f"{PROJECT_DIR}/scripts/report_frontend.json"


def log(msg):
    print(f"[frontend-agent] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


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


def run_docker_cmd(cmd_list):
    base = ["docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml",
            "exec", "-T", "iatronix-frontend"]
    result = subprocess.run(base + cmd_list, capture_output=True, text=True,
                            cwd=PROJECT_DIR, timeout=180)
    return result.stdout + result.stderr, result.returncode


def run_tsc():
    return run_docker_cmd(["npx", "tsc", "--noEmit", "--pretty", "false"])


def run_lint():
    return run_docker_cmd(["npx", "next", "lint", "--format", "json"])


def find_dead_features():
    """Find frontend fetch() calls and check if they map to real backend routes."""
    frontend_src = f"{PROJECT_DIR}/frontend/src"
    backend_routes = set()

    # Collect backend routes
    for py_file in glob.glob(f"{PROJECT_DIR}/backend/app/api/**/*.py", recursive=True):
        try:
            with open(py_file) as f:
                content = f.read()
            # Extract route paths from decorators
            for m in re.finditer(r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)', content):
                backend_routes.add(m.group(2))
        except Exception:
            pass

    # Find frontend API calls
    dead = []
    for ts_file in glob.glob(f"{frontend_src}/**/*.{'{ts,tsx}'}", recursive=True):
        try:
            with open(ts_file) as f:
                content = f.read()
        except Exception:
            continue
        # Find fetch calls to /api/v1/...
        for m in re.finditer(r'fetch\([`"\'](/api/v1/[^`"\'?\s]+)', content):
            path = m.group(1)
            # Strip /api/v1 prefix and check against backend routes
            route = path.replace("/api/v1", "")
            # Check if any backend route is a prefix match
            matched = any(
                route.startswith(r.split("{")[0].rstrip("/")) or r == route
                for r in backend_routes
            )
            if not matched:
                dead.append({"file": ts_file.replace(PROJECT_DIR + "/", ""), "path": path})

    return dead, sorted(backend_routes)


def run():
    log("Starting frontend test agent")
    report = {"tsc": {}, "lint": {}, "dead_features": [], "analysis": ""}

    # TypeScript check
    log("Running TypeScript type check")
    tsc_out, tsc_rc = run_tsc()
    report["tsc"] = {"exit": tsc_rc, "output": tsc_out[-3000:]}
    log(f"  TSC exit={tsc_rc}, errors={tsc_out.count('error TS')}")

    # Lint
    log("Running ESLint")
    lint_out, lint_rc = run_lint()
    report["lint"] = {"exit": lint_rc, "output": lint_out[-2000:]}
    log(f"  Lint exit={lint_rc}")

    # Dead features
    log("Checking for dead features (frontend calls with no backend route)")
    dead, backend_routes = find_dead_features()
    report["dead_features"] = dead
    report["backend_routes_found"] = len(backend_routes)
    log(f"  Backend routes found: {len(backend_routes)}")
    log(f"  Potentially dead frontend calls: {len(dead)}")
    for d in dead:
        log(f"    {d['file']}: {d['path']}")

    # Ask Ollama for analysis
    issues_summary = f"""
TypeScript errors: {tsc_out.count('error TS')} (exit={tsc_rc})
TSC output tail: {tsc_out[-1500:]}

ESLint exit: {lint_rc}
Lint output: {lint_out[-800:]}

Potentially dead frontend API calls ({len(dead)} found):
{json.dumps(dead, indent=2)[:500]}
"""
    log("Asking Ollama to analyse frontend issues")
    analysis = ollama(
        f"Analyse these frontend issues for a Next.js 15 medical AI app:\n\n{issues_summary}\n\n"
        f"List the top issues and exact fixes needed. Be specific.",
        context="You are a TypeScript/Next.js expert reviewing a medical AI frontend."
    )
    report["analysis"] = analysis
    log(f"  Analysis: {analysis[:400]}")

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    log(f"Report written to {REPORT_FILE}")
    return report


if __name__ == "__main__":
    run()
