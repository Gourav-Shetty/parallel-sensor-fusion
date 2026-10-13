"""Flask dashboard backend: streams fused sensor result in real time.

Native Windows (works TODAY, no Ubuntu needed):
    pip install flask numpy
    python app.py  ->  http://127.0.0.1:5000

WSL Ubuntu proper MPI mode (graded path):
    mpirun -np 4 python3 sensor_mpi.py --ticks 60   # headless proof
    # plus dashboard still served from here via /stream (fallback pool)

Endpoints:
    GET  /                 dashboard
    GET  /stream?sensors=N&ticks=T&workers=W   SSE live ticks (pool mode)
    POST /api/benchmark    {sensors, ticks, heavy_iters, workers}
                           -> {seq_s, par_s, speedup, fused_sample}
    POST /api/mpi-run      {sensors, ticks} -> real mpiexec run, Rank-0 rows
    GET  /api/mpi-status   -> {mpiexec_found, mpi4py_found}
"""
import json
import os
import shutil
import subprocess
import sys
import time

from flask import Flask, Response, jsonify, render_template, request

from sensor_core import run_parallel_pool, run_sequential

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def find_mpiexec():
    """Locate a real MPI launcher (PATH + Intel impi-rt wheel layout)."""
    for name in ("mpiexec", "mpirun"):
        hit = shutil.which(name)
        if hit:
            return hit
    bundled = os.path.join(sys.prefix, "Library", "bin", "mpiexec.exe")
    if os.path.isfile(bundled):
        return bundled
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/mpi-status")
def mpi_status():
    try:
        import mpi4py  # noqa: F401
        mpi4py_found = True
    except Exception:
        mpi4py_found = False
    return jsonify({
        "mpiexec_found": find_mpiexec() is not None,
        "mpiexec_path": find_mpiexec(),
        "mpirun_found": shutil.which("mpirun") is not None,
        "mpi4py_found": mpi4py_found,
    })


@app.route("/api/mpi-run", methods=["POST"])
def mpi_run():
    """Run the REAL MPI job (mpiexec -n N sensor_mpi.py) and return rows.

    This is genuine MPI: N OS processes, one rank each, Rank 0 reduces
    with comm.reduce(SUM/MAX/MIN). Takes ~seconds; capped for classroom.
    """
    body = request.get_json(force=True, silent=True) or {}
    n = max(1, min(int(body.get("sensors", 4)), 8))
    ticks = max(1, min(int(body.get("ticks", 10)), 30))
    exe = find_mpiexec()
    if exe is None:
        return jsonify({"ok": False,
                        "error": "no MPI launcher found (pip install mpi4py impi-rt)"}), 400
    cmd = [exe, "-n", str(n), sys.executable, "sensor_mpi.py",
           "--ticks", str(ticks), "--delay", "0"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=180, cwd=BASE_DIR)
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "MPI run timed out"}), 500
    rows = []
    for ln in (p.stdout or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            rows.append({"raw": ln})
    return jsonify({"ok": p.returncode == 0, "launcher": exe,
                    "ranks": n, "returncode": p.returncode,
                    "stderr": (p.stderr or "")[-2000:], "rows": rows})


@app.route("/stream")
def stream():
    sensors = max(1, min(int(request.args.get("sensors", 4)), 8))
    ticks = max(1, min(int(request.args.get("ticks", 60)), 500))
    workers = max(1, min(int(request.args.get("workers", 4)), 8))
    heavy = max(500, min(int(request.args.get("heavy", 20000)), 200000))

    def gen():
        # stream tick-by-tick using parallel pool per tick so the
        # browser sees real-time fusion + the server uses all cores
        from concurrent.futures import ProcessPoolExecutor
        from sensor_core import combine_measurements, simulate_one_sensor
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for t in range(ticks):
                futs = [pool.submit(simulate_one_sensor, s, t, 25.0, heavy)
                        for s in range(sensors)]
                readings = [f.result() for f in futs]
                fused = combine_measurements(readings)
                yield f"data: {json.dumps({'tick': t, 'sensors': readings, 'fused': fused})}\n\n"
                time.sleep(0.3)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/api/benchmark", methods=["POST"])
def benchmark():
    body = request.get_json(force=True, silent=True) or {}
    sensors = int(body.get("sensors", 4))
    ticks = int(body.get("ticks", 10))
    heavy = int(body.get("heavy_iters", 30000))
    workers = int(body.get("workers", 4))
    sensors = max(1, min(sensors, 8))
    ticks = max(1, min(ticks, 30))

    t0 = time.perf_counter()
    seq = run_sequential(sensors, ticks, heavy_iters=heavy)
    seq_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    par = run_parallel_pool(sensors, ticks, heavy_iters=heavy, workers=workers)
    par_s = time.perf_counter() - t0

    speedup = round(seq_s / par_s, 2) if par_s > 0 else 0.0
    return jsonify({
        "sensors": sensors, "ticks": ticks, "workers": workers,
        "heavy_iters": heavy,
        "sequential_s": round(seq_s, 3),
        "parallel_s": round(par_s, 3),
        "speedup": speedup,
        "fused_sample": par[-1]["fused"] if par else seq[-1]["fused"],
        "note": ("MPI_Reduce equivalent: sum/max/min across ranks, "
                 "avg = sum/count on rank 0."),
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
