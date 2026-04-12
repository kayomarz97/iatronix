#!/usr/bin/env python3
"""
Security agent — scans backend for OWASP Top 10 issues, auth weaknesses,
injection risks. Uses Ollama for analysis. Writes security report.
"""

import subprocess, json, glob, re, urllib.request, os, sys
from datetime import datetime

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen2.5:3b"
PROJECT_DIR = "/root/projects/med-ai-project"
REPORT_FILE = f"{PROJECT_DIR}/scripts/report_security.json"
BACKEND     = f"{PROJECT_DIR}/backend/app"


def log(msg):
    print(f"[security-agent] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def ollama(prompt, context=""):
    messages = []
    if context:
        messages.append({"role": "system", "content": context})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": MODEL, "messages": messages, "stream": False,
        "options": {"num_predict": 1024, "temperature": 0.1}
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["message"]["content"]
    except Exception as e:
        return f"[ollama error: {e}]"


def read_file(path):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return ""


def grep_pattern(pattern, directory, file_glob="*.py"):
    """Return list of (file, line_no, line) matches."""
    matches = []
    for fpath in glob.glob(f"{directory}/**/{file_glob}", recursive=True):
        try:
            with open(fpath) as f:
                for i, line in enumerate(f, 1):
                    if re.search(pattern, line):
                        rel = fpath.replace(PROJECT_DIR + "/", "")
                        matches.append({"file": rel, "line": i, "content": line.strip()})
        except Exception:
            pass
    return matches


def scan_injection_risks():
    """Look for potential injection patterns."""
    return {
        "raw_sql":       grep_pattern(r'execute\s*\(\s*[f"\'`].*SELECT|INSERT|UPDATE|DELETE', BACKEND),
        "format_in_sql": grep_pattern(r'\.format\(.*\)|f".*{.*}.*".*WHERE', BACKEND),
        "os_system":     grep_pattern(r'os\.system|subprocess\.call.*shell=True', BACKEND),
        "eval_exec":     grep_pattern(r'\beval\s*\(|\bexec\s*\(', BACKEND),
    }


def scan_auth_issues():
    """Check auth endpoint files for security issues."""
    auth_file    = f"{BACKEND}/api/v1/auth_routes.py"
    byok_file    = f"{BACKEND}/services/byok.py"
    mw_file      = f"{BACKEND}/middleware/rate_limit.py"
    schema_file  = f"{BACKEND}/schemas/auth.py"
    return {
        "auth_routes":  read_file(auth_file)[:3000],
        "byok_service": read_file(byok_file)[:2000],
        "rate_limit_mw": read_file(mw_file)[:2000],
        "auth_schemas": read_file(schema_file)[:1500],
    }


def scan_secrets_in_code():
    """Find hardcoded secrets."""
    patterns = [
        r'password\s*=\s*["\'][^"\']{8,}',
        r'secret\s*=\s*["\'][^"\']{8,}',
        r'api_key\s*=\s*["\']sk-',
        r'CHANGE_ME',
    ]
    hits = []
    for p in patterns:
        hits.extend(grep_pattern(p, BACKEND))
    return hits


def scan_headers():
    """Check security headers config."""
    return grep_pattern(r'add_header|X-Frame|HSTS|CSP|X-Content', PROJECT_DIR, "*.conf")


def scan_deps_for_vulns():
    """Run pip-audit if available."""
    result = subprocess.run(
        ["docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml",
         "exec", "-T", "iatronix-backend", "pip", "list", "--format=json"],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=30
    )
    return result.stdout[:3000]


def run():
    log("Starting security agent")
    report = {}

    log("Scanning injection risks")
    report["injection"] = scan_injection_risks()
    inj_count = sum(len(v) for v in report["injection"].values())
    log(f"  Found {inj_count} potential injection patterns")

    log("Scanning auth code")
    auth_code = scan_auth_issues()

    log("Scanning for hardcoded secrets")
    report["secrets"] = scan_secrets_in_code()
    log(f"  Found {len(report['secrets'])} potential secret patterns")

    log("Scanning nginx security headers")
    report["headers"] = scan_headers()

    log("Checking installed packages")
    pkg_list = scan_deps_for_vulns()
    report["packages_snapshot"] = pkg_list[:1000]

    # Collate issues for Ollama analysis
    issues_text = f"""
INJECTION RISKS ({inj_count} patterns found):
{json.dumps(report['injection'], indent=2)[:1500]}

AUTH CODE (auth_routes.py excerpt):
{auth_code['auth_routes'][:1500]}

BYOK SERVICE (byok.py excerpt):
{auth_code['byok_service'][:800]}

HARDCODED SECRETS ({len(report['secrets'])} found):
{json.dumps(report['secrets'][:10], indent=2)[:500]}

NGINX SECURITY HEADERS:
{json.dumps(report['headers'][:5], indent=2)[:400]}
"""

    log("Asking Ollama for security analysis")
    analysis = ollama(
        f"Perform a security review of this FastAPI medical AI backend code.\n\n{issues_text}\n\n"
        "List the top 5 security vulnerabilities (OWASP Top 10 focus) with:\n"
        "1. Severity (Critical/High/Medium/Low)\n"
        "2. Vulnerability type\n"
        "3. Exact location (file + line)\n"
        "4. Recommended fix\n"
        "Be specific and prioritize real risks over false positives.",
        context="You are an application security expert (OWASP, SANS) reviewing a healthcare API."
    )
    report["analysis"] = analysis
    log(f"  Security analysis:\n{analysis[:600]}")

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    log(f"Report written to {REPORT_FILE}")
    return report


if __name__ == "__main__":
    run()
