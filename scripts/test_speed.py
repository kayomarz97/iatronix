#!/usr/bin/env python3
"""
Speed agent — measures backend response latency, frontend bundle size,
DB query times, cache hit rates. Uses Ollama to suggest optimizations.
"""

import subprocess, json, urllib.request, time, re, glob, os
from datetime import datetime

OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "qwen2.5:3b"
PROJECT_DIR = "/root/projects/med-ai-project"
REPORT_FILE = f"{PROJECT_DIR}/scripts/report_speed.json"
BACKEND_URL = "http://localhost:8200"


def log(msg):
    print(f"[speed-agent] {datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


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


def measure_endpoint(path, method="GET", data=None, headers=None, n=3):
    """Measure average response time for an endpoint."""
    times = []
    for _ in range(n):
        try:
            req = urllib.request.Request(
                f"{BACKEND_URL}{path}",
                data=data,
                headers=headers or {},
                method=method
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=10) as r:
                status = r.status
                r.read()
            times.append(time.time() - t0)
        except Exception as e:
            times.append(None)
    valid = [t for t in times if t is not None]
    return {
        "path": path,
        "avg_ms": round(sum(valid) / len(valid) * 1000) if valid else None,
        "min_ms": round(min(valid) * 1000) if valid else None,
        "max_ms": round(max(valid) * 1000) if valid else None,
        "success_rate": f"{len(valid)}/{n}",
    }


def measure_frontend_bundle():
    """Check .next build output sizes."""
    next_dir = f"{PROJECT_DIR}/frontend/.next"
    if not os.path.exists(next_dir):
        return {"error": ".next directory not found — container may not have built"}
    sizes = {}
    for js_file in glob.glob(f"{next_dir}/static/chunks/*.js"):
        size_kb = os.path.getsize(js_file) / 1024
        if size_kb > 100:  # Only report large chunks
            sizes[os.path.basename(js_file)] = round(size_kb, 1)
    total = sum(
        os.path.getsize(f) for f in glob.glob(f"{next_dir}/static/**/*", recursive=True)
        if os.path.isfile(f)
    )
    return {
        "total_static_kb": round(total / 1024, 1),
        "large_chunks_kb": dict(sorted(sizes.items(), key=lambda x: -x[1])[:10]),
    }


def check_docker_stats():
    """Get Docker container resource usage."""
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format",
         "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"],
        capture_output=True, text=True, timeout=15
    )
    return result.stdout.strip()


def check_db_slow_queries():
    """Check PostgreSQL for slow query stats."""
    cmd = ["docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml",
           "exec", "-T", "iatronix-db",
           "psql", "-U", "medadmin", "-d", "medvectordb", "-c",
           "SELECT query, calls, mean_exec_time::int as avg_ms, max_exec_time::int as max_ms "
           "FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=PROJECT_DIR, timeout=15)
    return result.stdout + result.stderr


def check_redis_stats():
    """Check Redis memory and hit rate."""
    cmd = ["docker", "compose", "-f", f"{PROJECT_DIR}/docker-compose.yml",
           "exec", "-T", "iatronix-redis",
           "redis-cli", "INFO", "stats"]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=PROJECT_DIR, timeout=10)
    info = {}
    for line in result.stdout.splitlines():
        if ":" in line and not line.startswith("#"):
            k, _, v = line.partition(":")
            info[k.strip()] = v.strip()
    return {k: info.get(k) for k in
            ["keyspace_hits", "keyspace_misses", "used_memory_human",
             "total_commands_processed", "connected_clients"]}


def read_file_excerpt(path, lines=80):
    try:
        with open(path) as f:
            content = f.readlines()
        return "".join(content[:lines])
    except Exception:
        return ""


def run():
    log("Starting speed agent")
    report = {}

    # API latency
    log("Measuring API endpoint latency")
    report["api_latency"] = [
        measure_endpoint("/api/v1/health"),
        measure_endpoint("/api/v1/models"),
    ]
    for m in report["api_latency"]:
        log(f"  {m['path']}: avg={m['avg_ms']}ms")

    # Frontend bundle
    log("Checking frontend bundle sizes")
    report["bundle"] = measure_frontend_bundle()
    log(f"  Total static: {report['bundle'].get('total_static_kb', '?')} KB")

    # Docker stats
    log("Checking Docker resource usage")
    report["docker_stats"] = check_docker_stats()
    log(f"  {report['docker_stats'][:200]}")

    # DB slow queries
    log("Checking DB slow queries")
    report["db_slow_queries"] = check_db_slow_queries()

    # Redis stats
    log("Checking Redis cache stats")
    report["redis"] = check_redis_stats()
    hits = report["redis"].get("keyspace_hits", "0")
    misses = report["redis"].get("keyspace_misses", "0")
    log(f"  Redis: hits={hits}, misses={misses}")

    # Read key performance-sensitive files for context
    pipeline_excerpt = read_file_excerpt(
        f"{PROJECT_DIR}/backend/app/services/rag_pipeline.py", 100
    )
    session_excerpt = read_file_excerpt(
        f"{PROJECT_DIR}/backend/app/db/session.py"
    )

    perf_context = f"""
API LATENCY:
{json.dumps(report['api_latency'], indent=2)}

FRONTEND BUNDLE:
{json.dumps(report['bundle'], indent=2)[:500]}

DOCKER STATS:
{report['docker_stats'][:300]}

REDIS CACHE:
{json.dumps(report['redis'], indent=2)}

DB SLOW QUERIES:
{report['db_slow_queries'][:500]}

RAG PIPELINE (excerpt):
{pipeline_excerpt[:800]}

DB SESSION CONFIG:
{session_excerpt[:500]}
"""

    log("Asking Ollama for speed optimization analysis")
    analysis = ollama(
        f"Analyse performance metrics for a FastAPI medical AI backend:\n\n{perf_context}\n\n"
        "List the top 5 performance improvements with:\n"
        "1. Impact (High/Medium/Low)\n"
        "2. What to change (file + function)\n"
        "3. Expected improvement\n"
        "4. Code snippet if applicable\n"
        "Focus on quick wins first.",
        context="You are a backend performance engineer specializing in Python/FastAPI/PostgreSQL."
    )
    report["analysis"] = analysis
    log(f"  Speed analysis:\n{analysis[:500]}")

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    log(f"Report written to {REPORT_FILE}")
    return report


if __name__ == "__main__":
    run()
