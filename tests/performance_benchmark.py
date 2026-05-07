
import asyncio
import httpx
import time
import statistics
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

QUERIES = [
    "what is the main contribution of DeepSketch?",
    "latest advancements in graph neural networks from 2025",
    "compare transformer and mamba architectures",
    "who are the authors of the attention is all you need paper?",
    "list papers about multi-agent reinforcement learning from 2024",
    "timeline of large language models",
    "survey of efficient fine-tuning methods",
    "does graphrag improve retrieval accuracy?",
    "trending papers in computer vision",
    "hello how are you"
]

async def call_endpoint(client, endpoint, payload, method="POST"):
    t0 = time.perf_counter()
    try:
        if method == "POST":
            resp = await client.post(f"{BASE_URL}{endpoint}", json=payload)
        else:
            resp = await client.get(f"{BASE_URL}{endpoint}", params=payload)
        
        latency = (time.perf_counter() - t0) * 1000
        return {
            "endpoint": endpoint,
            "status": resp.status_code,
            "latency_ms": latency,
            "success": resp.status_code == 200,
            "error": resp.text if resp.status_code != 200 else None,
            "request_id": resp.json().get("request_id") if resp.status_code == 200 else None,
            "route": resp.json().get("route") if resp.status_code == 200 else "unknown"
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "status": 500,
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "success": False,
            "error": str(e),
            "route": "error"
        }

async def run_benchmark():
    print(f"Starting Aether v6.0 Performance Benchmark for {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("-" * 50)

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Warmup
        print("Warming up...")
        await call_endpoint(client, "/api/health", {}, method="GET")
        
        # 2. Sequential Latency Test
        print("\nPhase 1: Sequential Latency Test")
        results = []
        for q in QUERIES:
            print(f"  Testing query: {q[:40]}...")
            payload = {
                "query": q,
                "top_k": 5,
                "min_similarity": 0.25,
                "use_heavy": False,
                "verify": True
            }
            res = await call_endpoint(client, "/api/research", payload)
            results.append(res)
            metrics = res.get("latency_metrics", {})
            metrics_str = " | ".join([f"{k}: {v}ms" for k, v in metrics.items() if v > 0 and k != "total_ms"])
            print(f"    - {'OK' if res['success'] else 'FAIL'} | {res['latency_ms']:.0f}ms | route: {res['route']}")
            if metrics_str:
                print(f"      [{metrics_str}]")

        # 3. Concurrent Load Test
        print("\nPhase 2: Concurrent Load Test (3 simultaneous requests)")
        t0 = time.perf_counter()
        concurrent_results = await asyncio.gather(*[
            call_endpoint(client, "/api/research", {
                "query": QUERIES[i % len(QUERIES)],
                "top_k": 5
            })
            for i in range(3)
        ])
        total_time = (time.perf_counter() - t0) * 1000
        print(f"  Completed 3 requests in {total_time:.0f}ms")
        for i, res in enumerate(concurrent_results):
             print(f"    - Req {i+1}: {'OK' if res['success'] else 'FAIL'} | {res['latency_ms']:.0f}ms")

        # 4. Statistics
        all_results = results + concurrent_results
        latencies = [r["latency_ms"] for r in all_results if r["success"]]
        
        if latencies:
            print("\n" + "=" * 50)
            print("PERFORMANCE SUMMARY")
            print("=" * 50)
            print(f"Total Requests: {len(all_results)}")
            print(f"Success Rate:   {len(latencies)/len(all_results):.1%}")
            print(f"Avg Latency:    {statistics.mean(latencies):.1f} ms")
            print(f"Min Latency:    {min(latencies):.1f} ms")
            print(f"Max Latency:    {max(latencies):.1f} ms")
            if len(latencies) > 1:
                print(f"Std Dev:        {statistics.stdev(latencies):.1f} ms")
            print("-" * 50)
        else:
            print("\n[ERROR] No successful requests to calculate stats.")

        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(all_results),
                "success": len(latencies),
                "avg_ms": statistics.mean(latencies) if latencies else 0
            },
            "detailed_results": all_results
        }
        with open("performance_report.json", "w") as f:
            json.dump(report, f, indent=2)
        print(f"Full report saved to performance_report.json")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
