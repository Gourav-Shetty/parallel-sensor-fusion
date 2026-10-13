"""Shared sensor simulation + reduction logic.

Used by:
- sensor_mpi.py (proper MPI mode in WSL / MS-MPI)
- app.py (native Windows fallback via ProcessPoolExecutor + sequential baseline)

Each "distributed measurement" is a noisy temperature reading with
CPU-heavy filtering so parallel speedup is visible in benchmarks.
"""
import math
import random


def simulate_one_sensor(sensor_id: int, tick: int, base_temp: float = 25.0,
                        heavy_iters: int = 20000) -> float:
    """Simulate one distributed sensor reading at a given tick.

    Includes deterministic drift per sensor + random noise + CPU work
    (moving-average style filtering loop) to make parallelism measurable.
    """
    rng = random.Random(sensor_id * 100000 + tick)
    # per-sensor bias + slow drift + noise
    bias = (sensor_id - 2) * 1.5
    drift = 2.0 * math.sin(tick / 10.0 + sensor_id)
    noise = rng.gauss(0, 0.8)
    raw = base_temp + bias + drift + noise

    # CPU-heavy filtering stand-in (parallelism demo workload)
    # Keeps result near raw (~25 C) so the dashboard looks realistic.
    acc = 0.0
    for i in range(heavy_iters):
        acc += raw + 0.5 * math.sin(i * 0.001 + sensor_id) * math.cos(tick * 0.1)
    filtered = acc / heavy_iters
    return round(filtered, 3)


def combine_measurements(values) -> dict:
    """Reduce distributed measurements into ONE result (like MPI_Reduce)."""
    values = list(values)
    if not values:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "count": 0}
    return {
        "avg": round(sum(values) / len(values), 3),
        "max": round(max(values), 3),
        "min": round(min(values), 3),
        "count": len(values),
    }


def run_sequential(num_sensors: int, ticks: int, heavy_iters: int = 20000):
    """Baseline: all sensors computed one-by-one in this process."""
    history = []
    for t in range(ticks):
        readings = [simulate_one_sensor(s, t, heavy_iters=heavy_iters)
                    for s in range(num_sensors)]
        fused = combine_measurements(readings)
        history.append({"tick": t, "sensors": readings, "fused": fused})
    return history


def run_parallel_pool(num_sensors: int, ticks: int, heavy_iters: int = 20000,
                      workers: int = 4):
    """Native-Windows parallel mode: ProcessPoolExecutor per tick."""
    from concurrent.futures import ProcessPoolExecutor
    history = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for t in range(ticks):
            futures = [pool.submit(simulate_one_sensor, s, t, 25.0, heavy_iters)
                       for s in range(num_sensors)]
            readings = [f.result() for f in futures]
            fused = combine_measurements(readings)
            history.append({"tick": t, "sensors": readings, "fused": fused})
    return history
