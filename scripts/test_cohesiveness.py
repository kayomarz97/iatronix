#!/usr/bin/env python3
"""
Cohesiveness agent — maps every frontend feature to its backend route,
identifies broken/orphaned UI, checks UX consistency, removes dead code.
Reports actionable cleanup items.
"""

import os, re, json, glob, urllib.request
from datetime import datetime

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen2.5:3b"
PROJECT_DIR = "/root/projects/med-ai-project"
REPORT_FILE = f"{PROJECT_DIR}/scripts/report_cohesiveness.json"
FRONTEND    = f"{PROJECT_DIR}/frontend/src"
BACKEND     = f"{PROJECT_DIR}/backend/app"


def log(msg):
    print(f"[cohesive-agent] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


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


def read(path):
    try:
        with open(path) as f: return f.read()
    except Exception: return ""


def collect_backend_routes():
    """Collect all registered FastAPI routes from API files."""
    routes = {}
    for py_file in glob.glob(f"{BACKEND}/api/**/*.py", recursive=True):
        content = read(py_file)
        rel = py_file.replace(PROJECT_DIR + "/", "")
        for m in re.finditer(
            r'@router\.(get|post|put|delete|patch)\(["\']([^"\']+)["\'].*?\n\s*(?:async\s+)?def\s+(\w+)',
            content, re.DOTALL
        ):
            method, path, func = m.group(1).upper(), m.group(2), m.group(3)
            # Get prefix from router declaration
            prefix_m = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', content)
            prefix = prefix_m.group(1) if prefix_m else ""
            full_path = "/api/v1" + prefix + path
            routes[full_path] = {"method": method, "func": func, "file": rel}
    return routes


def collect_frontend_api_calls():
    """Find all API calls in frontend code."""
    calls = []
    for ts_file in glob.glob(f"{FRONTEND}/**/*.ts", recursive=True):
        calls += _extract_calls(ts_file)
    for tsx_file in glob.glob(f"{FRONTEND}/**/*.tsx", recursive=True):
        calls += _extract_calls(tsx_file)
    return calls


def _extract_calls(fpath):
    content = read(fpath)
    rel = fpath.replace(PROJECT_DIR + "/", "")
    calls = []
    # Direct fetch calls
    for m in re.finditer(r'fetch\([`"\']([^`"\'?\s]+)', content):
        path = m.group(1)
        if path.startswith("/api"):
            calls.append({"file": rel, "path": path, "type": "fetch"})
    # Template literal paths
    for m in re.finditer(r'fetch\(`([^`]+)`', content):
        path = m.group(1).split("?")[0]
        if "/api" in path:
            # Normalize template params
            path = re.sub(r'\$\{[^}]+\}', '{id}', path)
            calls.append({"file": rel, "path": path, "type": "fetch_template"})
    return calls


def find_unused_components():
    """Find components that are never imported."""
    component_files = glob.glob(f"{FRONTEND}/components/**/*.tsx", recursive=True)
    unused = []
    for comp_file in component_files:
        comp_name = os.path.splitext(os.path.basename(comp_file))[0]
        rel = comp_file.replace(PROJECT_DIR + "/", "")
        # Search for imports of this component
        found = False
        for ts_file in glob.glob(f"{FRONTEND}/**/*.{'{ts,tsx}'}", recursive=True):
            if ts_file == comp_file:
                continue
            content = read(ts_file)
            if comp_name in content:
                found = True
                break
        if not found:
            unused.append({"component": comp_name, "file": rel})
    return unused


def check_nav_links():
    """Check that nav links in Header/MobileNav point to real pages."""
    header = read(f"{FRONTEND}/components/layout/Header.tsx")
    mobile = read(f"{FRONTEND}/components/layout/MobileNav.tsx")
    nav_links = re.findall(r'href=["\']([^"\']+)["\']', header + mobile)
    pages = [
        f.replace(f"{FRONTEND}/app", "").replace("/page.tsx", "") or "/"
        for f in glob.glob(f"{FRONTEND}/app/**/page.tsx", recursive=True)
    ]
    dead_links = [l for l in nav_links if l.startswith("/") and l not in pages and not l.startswith("/api")]
    return {"nav_links": nav_links, "pages": pages, "dead_links": dead_links}


def run():
    log("Starting cohesiveness agent")
    report = {}

    log("Collecting backend routes")
    backend_routes = collect_backend_routes()
    report["backend_route_count"] = len(backend_routes)
    log(f"  Found {len(backend_routes)} backend routes")

    log("Collecting frontend API calls")
    frontend_calls = collect_frontend_api_calls()
    report["frontend_call_count"] = len(frontend_calls)
    log(f"  Found {len(frontend_calls)} frontend API calls")

    # Cross-reference
    orphaned = []
    for call in frontend_calls:
        path = call["path"]
        # Normalize: strip trailing slash, query params
        normalized = path.rstrip("/").split("?")[0]
        # Check if path matches any backend route (with wildcards for {id})
        matched = False
        for route_path in backend_routes:
            route_pattern = re.sub(r'\{[^}]+\}', '[^/]+', route_path)
            if re.fullmatch(route_pattern.rstrip("/"), normalized.rstrip("/")):
                matched = True
                break
            # Also match prefix patterns
            if normalized.startswith(route_path.split("{")[0].rstrip("/")):
                matched = True
                break
        if not matched:
            orphaned.append(call)

    report["orphaned_calls"] = orphaned
    log(f"  Orphaned frontend calls (no matching backend): {len(orphaned)}")
    for o in orphaned:
        log(f"    {o['file']}: {o['path']}")

    log("Finding unused components")
    unused_comps = find_unused_components()
    report["unused_components"] = unused_comps
    log(f"  Unused components: {len(unused_comps)}")
    for u in unused_comps:
        log(f"    {u['file']}")

    log("Checking nav link integrity")
    nav = check_nav_links()
    report["nav"] = nav
    log(f"  Dead nav links: {nav['dead_links']}")

    # Read page files for context
    pages_content = {}
    for page in ["query", "settings", "documents", "about"]:
        pf = f"{FRONTEND}/app/{page}/page.tsx"
        if os.path.exists(pf):
            pages_content[page] = read(pf)[:500]

    cohesion_context = f"""
BACKEND ROUTES ({len(backend_routes)} total):
{json.dumps(list(backend_routes.keys())[:30], indent=2)}

ORPHANED FRONTEND CALLS ({len(orphaned)} — no matching backend):
{json.dumps(orphaned, indent=2)[:800]}

UNUSED COMPONENTS ({len(unused_comps)}):
{json.dumps(unused_comps, indent=2)[:400]}

DEAD NAV LINKS: {nav['dead_links']}

PAGE SUMMARIES:
{json.dumps({k: v[:200] for k, v in pages_content.items()}, indent=2)[:600]}
"""

    log("Asking Ollama for cohesiveness analysis")
    analysis = ollama(
        f"Analyse frontend/backend cohesiveness for a Next.js 15 + FastAPI medical app:\n\n"
        f"{cohesion_context}\n\n"
        "List:\n"
        "1. Which frontend features have no working backend (remove or stub)\n"
        "2. Which components are dead code (safe to delete)\n"
        "3. Any UX inconsistencies between pages\n"
        "4. Missing error states or loading states\n"
        "Be specific with file names and recommended actions.",
        context="You are a fullstack engineer reviewing frontend/backend cohesiveness."
    )
    report["analysis"] = analysis
    log(f"  Analysis:\n{analysis[:500]}")

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    log(f"Report written to {REPORT_FILE}")
    return report


if __name__ == "__main__":
    run()
