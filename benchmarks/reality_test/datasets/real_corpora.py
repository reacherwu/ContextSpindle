"""Real-Text Benchmark Corpora for AIOps, GitHub Agent, and Persona Dialogue."""

from __future__ import annotations

import random
from typing import NamedTuple


class CorpusItem(NamedTuple):
    timestamp: float
    event_id: int
    text: str
    is_root_cause: bool
    category: str


def generate_aiops_log_corpus(n_events: int = 3000, seed: int = 42) -> tuple[list[CorpusItem], str, int]:
    """
    Simulates a 24-hour enterprise microservice log stream.
    At t=100: Silent configuration drift (DB pool size reduction from 50 to 5).
    At t=101..2899: Routine nginx, k8s, redis, and worker health logs.
    At t=2900..2999: Alert storm of 504 timeouts and connection pool exhaustion.
    """
    rng = random.Random(seed)
    items: list[CorpusItem] = []

    root_id = 100
    root_text = "[2026-09-14 02:15:22] [config-daemon] [AUTH-SERVICE] Updated db_connection_pool_size from 50 to 5. Idle_timeout set to 10s. Git commit #8421a9 by dev-alice."

    services = ["order-api", "payment-service", "inventory-worker", "search-indexer", "user-profile"]
    endpoints = ["/v1/health", "/metrics", "/v1/cart/sync", "/internal/ping", "/status"]

    for t in range(n_events):
        if t == root_id:
            items.append(CorpusItem(float(t), t, root_text, True, "config_change"))
        elif t >= 2900:
            # Alert storm
            svc = rng.choice(services)
            code = rng.choice([504, 502, 500])
            txt = f"[2026-09-14 21:58:{t%60:02d}] [CRITICAL] [{svc.upper()}] HTTP {code} Gateway Timeout: database connection pool exhausted, active_leases=5 max_leases=5 queue_depth={rng.randint(200, 1000)}"
            items.append(CorpusItem(float(t), t, txt, False, "alert_storm"))
        else:
            # Routine heartbeats and access logs
            svc = rng.choice(services)
            ep = rng.choice(endpoints)
            lat = rng.randint(5, 30)
            txt = f"[2026-09-14 {t//120:02d}:{(t//2)%60:02d}:{t%60:02d}] [INFO] [{svc.upper()}] GET {ep} status=200 latency={lat}ms worker_threads=8 memory_rss={rng.randint(180, 240)}MB"
            items.append(CorpusItem(float(t), t, txt, False, "routine_heartbeat"))

    query_text = "Cluster incident: 504 Gateway Timeout in checkout service caused by database connection pool exhausted"
    return items, query_text, root_id


def generate_github_trajectory_corpus(n_events: int = 100, seed: int = 42) -> tuple[list[CorpusItem], str, int]:
    """
    Simulates a 100-step autonomous coding agent trajectory.
    Step 10: Modifies SSL legacy configuration.
    Steps 11..89: Generates code modules, runs linters, database migrations.
    Step 90: Integration test fails with TLS handshake error.
    """
    rng = random.Random(seed)
    items: list[CorpusItem] = []

    root_id = 10
    root_text = "Step 10: Executed 'export OPENSSL_CONF=/etc/ssl/legacy.cnf' and updated openssl.conf with CipherString=DEFAULT@SECLEVEL=1 to allow legacy crypto."

    modules = ["auth", "billing", "users", "reports", "notifications", "utils", "storage"]

    for s in range(n_events):
        if s == root_id:
            items.append(CorpusItem(float(s), s, root_text, True, "agent_setup"))
        elif s >= 88:
            txt = f"Step {s}: Ran integration test suite 'pytest tests/integration/test_mutual_tls.py'. STDERR: SSLV3_ALERT_HANDSHAKE_FAILURE: unsupported protocol version during TLS handshake."
            items.append(CorpusItem(float(s), s, txt, False, "test_error"))
        else:
            mod = rng.choice(modules)
            action = rng.choice(["Added unit tests for", "Refactored database query in", "Generated API endpoints for", "Added pydantic schema for"])
            txt = f"Step {s}: {action} src/{mod}/service.py. Linter clean, 0 syntax errors."
            items.append(CorpusItem(float(s), s, txt, False, "routine_dev"))

    query_text = "Agent failure: integration test failed with TLS handshake failure SSLV3_ALERT_HANDSHAKE_FAILURE during mutual auth"
    return items, query_text, root_id


def generate_persona_dialogue_corpus(n_events: int = 2000, seed: int = 42) -> tuple[list[CorpusItem], str, int]:
    """
    Simulates a 2,000-turn multi-month personal AI companion chat.
    Turn 20: User gives critical life constraint (lethal peanut allergy).
    Turns 21..1979: Casual chitchat (movies, weather, work, weekend).
    Turns 1980..1999: Recent adventurous food chatter.
    Turn 2000 query: Book a surprise 5-course dinner.
    """
    rng = random.Random(seed)
    items: list[CorpusItem] = []

    root_id = 20
    root_text = "Turn 20: [USER] Please make a permanent note of this: I have a severe, potentially lethal peanut and tree-nut allergy. You must never recommend or book any food with nuts under any circumstances."

    topics = [
        "What do you think about the latest sci-fi movie that came out?",
        "Can you help me write a quick Python script to parse CSV files?",
        "The weather this weekend is going to be rainy, any indoor activity ideas?",
        "I went on a hike yesterday and walked 10 miles, feeling great!",
        "Do you know good keyboard shortcuts for VS Code on Mac?",
        "Let's discuss the plot of The Three-Body Problem book 2.",
    ]

    for t in range(n_events):
        if t == root_id:
            items.append(CorpusItem(float(t), t, root_text, True, "health_constraint"))
        elif t >= 1980:
            txt = f"Turn {t}: [USER] I'm feeling super adventurous today! Let's explore exotic gourmet food and spicy surprise tasting menus!"
            items.append(CorpusItem(float(t), t, txt, False, "recent_temptation"))
        else:
            q = rng.choice(topics)
            txt = f"Turn {t}: [USER] {q} [ASSISTANT] Here are some thoughts and recommendations on {q[:30]}..."
            items.append(CorpusItem(float(t), t, txt, False, "casual_chat"))

    query_text = "User prompt: Book a surprise 5-course tasting dinner tonight at the new gourmet bistro in town, check dietary safety restrictions"
    return items, query_text, root_id
