#!/usr/bin/env python3
"""Generate the synthetic Claude Code-style transcript used by `contextspindle fuse demo`.

Scenario (modeled on anthropics/claude-code#102666): a long debugging session where the
numbers survive compaction but the reasoning behind them does not. Deterministic output.
"""
import json, random
random.seed(7)
L = []
def user(text): L.append({"type": "user", "message": {"role": "user", "content": text}})
def asst(blocks):
    if isinstance(blocks, str): blocks = [{"type": "text", "text": blocks}]
    L.append({"type": "assistant", "message": {"role": "assistant", "content": blocks}})
def tool(tid, name, inp): return {"type": "tool_use", "id": tid, "name": name, "input": inp}
def result(tid, text): L.append({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}})
def noise(n):
    words = "fn let mut self return match Some None Ok Err impl struct pub use crate async await".split()
    return "\n".join(" ".join(random.choice(words) for _ in range(14)) for _ in range(n))

user("Find out why p99 latency of the checkout service regressed from 180 ms to 410 ms after release 2.14, and ship a fix. Don't change the public API of OrderClient. Keep the fix behind the flag checkout_pool_v2.")
asst([tool("todo1", "TodoWrite", {"todos": [
    {"content": "Reproduce the p99 regression locally", "status": "in_progress"},
    {"content": "Bisect release 2.14 changes", "status": "pending"},
    {"content": "Patch connection pool sizing behind checkout_pool_v2", "status": "pending"},
    {"content": "Run load test and compare p99", "status": "pending"}]})])
result("todo1", "Todos updated")
k = 0
for i in range(18):
    k += 1; tid = f"r{k}"
    asst([tool(tid, "Read", {"file_path": f"src/checkout/module_{i}.rs"})])
    result(tid, noise(60))
asst([tool("ag1", "Task", {"description": "Bisect release 2.14", "prompt": "Bisect commits between 2.13 and 2.14 for latency changes"})])
result("ag1", "Bisect result: commit 9f3c2e1 'reuse HTTP client per request' is the first bad commit. It creates a new hyper client per request, so the TLS handshake is repeated; handshakes account for ~230 ms at p99 in the trace.")
asst("Root cause is commit 9f3c2e1: a new client per request forces a fresh TLS handshake every time. We chose a shared pool of 32 connections instead of reverting, because the revert would also drop the retry fix from 2.14.")
asst([tool("todo2", "TodoWrite", {"todos": [
    {"content": "Reproduce the p99 regression locally", "status": "completed"},
    {"content": "Bisect release 2.14 changes", "status": "completed"},
    {"content": "Patch connection pool sizing behind checkout_pool_v2", "status": "in_progress"},
    {"content": "Run load test and compare p99", "status": "pending"}]})])
result("todo2", "Todos updated")
for i in range(18, 40):
    k += 1; tid = f"r{k}"
    asst([tool(tid, "Read", {"file_path": f"src/checkout/module_{i}.rs"})])
    result(tid, noise(60))
asst([tool("e1", "Edit", {"file_path": "src/checkout/client.rs", "old_string": "Client::new()", "new_string": "POOL.get()"})])
result("e1", "ok")
asst([tool("ag2", "Agent", {"description": "Load test with pool", "prompt": "Run k6 with 400 rps for 5 minutes"})])
result("ag2", "Load test: with checkout_pool_v2 on, p99 = 192 ms at 400 rps; with it off, p99 = 405 ms. No errors.")
asst("Ruled out the DNS resolver change in 2.14; resolver time is under 2 ms at p99. Next: run the soak test for 30 minutes before enabling the flag in staging.")
user("Good. Also, never enable the flag in production on a Friday.")
asst("Understood. Remaining work: the 30-minute soak test, then a staging rollout of checkout_pool_v2.")
with open("examples/fuse/session.jsonl", "w") as f:
    for x in L: f.write(json.dumps(x) + "\n")
