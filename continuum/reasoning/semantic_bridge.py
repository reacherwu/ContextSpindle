"""
Lightweight Semantic Causal Bridge (轻量语义因果桥接器).

Solves the fundamental "symptom-cause vocabulary gap" where symptoms describe
failure observations (e.g. 'SSLV3_ALERT_HANDSHAKE_FAILURE') while root causes describe
historical actions (e.g. 'updated openssl.conf with CipherString=DEFAULT@SECLEVEL=1').

Operates via Dual-Channel Query Projection:
  q_bridged = (1 - lambda) * q_symptom + lambda * q_hypotheses
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import torch
from torch import Tensor


@dataclass(frozen=True)
class DiagnosticExpansion:
    """Result of diagnostic causal expansion."""
    raw_query: str
    matched_domains: list[str]
    expanded_concepts: list[str]
    expansion_text: str
    explanation: str


class SemanticCausalBridge:
    """
    Lightweight Diagnostic Causal Expansion Engine.
    Maps observable symptoms to candidate root-cause mechanism spaces in < 1 ms.
    """
    def __init__(self) -> None:
        self._rules: list[tuple[re.Pattern, list[str], str]] = []
        self._init_default_causal_domains()

    def _init_default_causal_domains(self) -> None:
        """Register default engineering and systems causal mappings."""
        # 1. TLS / SSL / Crypto Handshake Failures
        self.register_pattern(
            r"(?i)(sslv3|tls|handshake|handshake_failure|cipher|certificate|ssl_error|bad_mac)",
            [
                "openssl",
                "crypto",
                "cipherstring",
                "seclevel",
                "legacy_crypto",
                "openssl_conf",
                "ssl_version",
                "certificate_authority",
                "mutual_tls",
            ],
            domain="tls_crypto_configuration",
        )

        # 2. Database Connection Pool Starvation & 504 Timeouts
        self.register_pattern(
            r"(?i)(504\s+gateway\s+timeout|connection\s+pool|pool\s+exhausted|active_leases|lease_timeout)",
            [
                "db_connection_pool_size",
                "idle_timeout",
                "max_connections",
                "database_pool",
                "auth_service_config",
                "postgres_pool",
                "redis_pool",
            ],
            domain="database_resource_limits",
        )

        # 3. OOM / Memory Pressure / Garbage Collection Thrashing
        self.register_pattern(
            r"(?i)(oomkilled|out\s+of\s+memory|memoryerror|sigkill|rss\s+exceeded)",
            [
                "memory_limit",
                "heap_size",
                "buffer_allocation",
                "memory_leak",
                "gc_pause",
                "cgroup_memory",
                "resource_quota",
            ],
            domain="memory_limits_and_leaks",
        )

        # 4. Networking & DNS Resolution Failures
        self.register_pattern(
            r"(?i)(econnrefused|connection\s+refused|broken\s+pipe|dns_resolution|host\s+not\s+found|502\s+bad\s+gateway)",
            [
                "port_binding",
                "iptables",
                "upstream_proxy",
                "service_discovery",
                "coredns",
                "routing_table",
                "ingress_config",
            ],
            domain="network_ingress_routing",
        )

        # 5. Permission & Authentication Invalidation
        self.register_pattern(
            r"(?i)(permission\s+denied|eacces|403\s+forbidden|unauthorized|jwt\s+expired)",
            [
                "chmod",
                "file_mode",
                "rbac_binding",
                "iam_policy",
                "api_key_rotation",
                "service_account",
                "token_refresh",
            ],
            domain="security_rbac_credentials",
        )

        # 6. Dietary, Allergy & Life Safety Constraints
        self.register_pattern(
            r"(?i)(dietary|allergy|allergic|restriction|restrictions|intolerance|safety\s+restrictions)",
            [
                "peanut",
                "tree_nut",
                "nuts",
                "allergy",
                "severe_allergy",
                "dietary_safety",
                "lethal_allergy",
            ],
            domain="dietary_health_constraints",
        )

    def register_pattern(self, pattern: str, concepts: list[str], domain: str) -> None:
        """Register a new causal association rule."""
        compiled = re.compile(pattern)
        self._rules.append((compiled, concepts, domain))

    def expand(self, query_text: str) -> DiagnosticExpansion:
        """
        Analyze symptom text and extract hypothesized causal mechanism concepts.
        """
        matched_domains: list[str] = []
        expanded_concepts: list[str] = []

        for pattern, concepts, domain in self._rules:
            if pattern.search(query_text):
                matched_domains.append(domain)
                for c in concepts:
                    if c not in expanded_concepts:
                        expanded_concepts.append(c)

        if not expanded_concepts:
            # Fallback: extract technical keywords
            words = re.findall(r"\b[A-Za-z0-9_-]{4,}\b", query_text.lower())
            expanded_concepts = words[:8]
            matched_domains.append("generic_technical_keywords")

        expansion_text = " ".join(expanded_concepts)
        explanation = (
            f"Expanded {len(expanded_concepts)} causal hypotheses across {len(matched_domains)} "
            f"domains: {', '.join(matched_domains)}"
        )

        return DiagnosticExpansion(
            raw_query=query_text,
            matched_domains=matched_domains,
            expanded_concepts=expanded_concepts,
            expansion_text=expansion_text,
            explanation=explanation,
        )

    def project_query(
        self,
        query_text: str,
        embedder: Any,
        lambda_weight: float = 0.50,
    ) -> tuple[Tensor, DiagnosticExpansion]:
        """
        Produce a dual-channel bridged query vector.
        q_bridged = (1 - lambda) * q_symptom + lambda * q_hypothesis
        """
        expansion = self.expand(query_text)

        v_symptom = embedder.embed(query_text).detach().float()
        v_hypothesis = embedder.embed(expansion.expansion_text).detach().float()

        # Normalize components
        norm_s = torch.norm(v_symptom, p=2)
        if norm_s > 1e-8:
            v_symptom = v_symptom / norm_s

        norm_h = torch.norm(v_hypothesis, p=2)
        if norm_h > 1e-8:
            v_hypothesis = v_hypothesis / norm_h

        # Dual-channel linear fusion
        v_bridged = (1.0 - lambda_weight) * v_symptom + lambda_weight * v_hypothesis
        norm_b = torch.norm(v_bridged, p=2)
        if norm_b > 1e-8:
            v_bridged = v_bridged / norm_b

        return v_bridged, expansion
