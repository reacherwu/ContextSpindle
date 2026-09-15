//! Native Semantic Causal Bridge in pure Rust.
//!
//! Bridges the symptom-cause vocabulary gap across domains (e.g. TLS handshake errors
//! to OpenSSL configuration changes) using dual-channel query projection in < 1 ms.

use crate::embedder::RealTextEmbedder;
use crate::math::normalize;

#[derive(Debug, Clone)]
pub struct DiagnosticExpansion {
    pub raw_query: String,
    pub matched_domains: Vec<String>,
    pub expanded_concepts: Vec<String>,
    pub expansion_text: String,
}

#[derive(Debug, Clone)]
pub struct SemanticCausalBridge {
    rules: Vec<(&'static [&'static str], &'static [&'static str], &'static str)>,
}

impl Default for SemanticCausalBridge {
    fn default() -> Self {
        Self::new()
    }
}

impl SemanticCausalBridge {
    pub fn new() -> Self {
        let rules: Vec<(&'static [&'static str], &'static [&'static str], &'static str)> = vec![
            // 1. TLS / SSL / Crypto Handshake Failures
            (
                &["sslv3", "tls", "handshake", "cipher", "certificate", "ssl_error", "bad_mac"],
                &[
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
                "tls_crypto_configuration",
            ),
            // 2. Database Connection Pool Starvation & 504 Timeouts
            (
                &["504", "gateway timeout", "connection pool", "pool exhausted", "active_leases"],
                &[
                    "db_connection_pool_size",
                    "idle_timeout",
                    "max_connections",
                    "database_pool",
                    "auth_service_config",
                    "postgres_pool",
                ],
                "database_resource_limits",
            ),
            // 3. Memory Pressure / OOM
            (
                &["oomkilled", "out of memory", "memoryerror", "sigkill", "rss exceeded"],
                &[
                    "memory_limit",
                    "heap_size",
                    "buffer_allocation",
                    "memory_leak",
                    "gc_pause",
                    "cgroup_memory",
                ],
                "memory_limits_and_leaks",
            ),
            // 4. Network Ingress & DNS Failures
            (
                &["econnrefused", "connection refused", "broken pipe", "dns", "502"],
                &[
                    "port_binding",
                    "iptables",
                    "upstream_proxy",
                    "service_discovery",
                    "coredns",
                    "ingress_config",
                ],
                "network_ingress_routing",
            ),
            // 5. Dietary, Allergy & Life Safety Constraints
            (
                &["dietary", "allergy", "allergic", "restriction", "restrictions", "intolerance", "safety restrictions"],
                &[
                    "peanut",
                    "tree_nut",
                    "nuts",
                    "allergy",
                    "severe_allergy",
                    "dietary_safety",
                    "lethal_allergy",
                ],
                "dietary_health_constraints",
            ),
        ];

        Self { rules }
    }

    /// Expands observable symptom text into candidate causal mechanism concepts.
    pub fn expand(&self, query_text: &str) -> DiagnosticExpansion {
        let lower = query_text.to_lowercase();
        let mut matched_domains = Vec::new();
        let mut expanded_concepts = Vec::new();

        for &(kws, concepts, domain) in &self.rules {
            let matched = kws.iter().any(|&kw| lower.contains(kw));
            if matched {
                matched_domains.push(domain.to_string());
                for &c in concepts {
                    let s = c.to_string();
                    if !expanded_concepts.contains(&s) {
                        expanded_concepts.push(s);
                    }
                }
            }
        }

        if expanded_concepts.is_empty() {
            matched_domains.push("generic_keywords".to_string());
        }

        let expansion_text = expanded_concepts.join(" ");

        DiagnosticExpansion {
            raw_query: query_text.to_string(),
            matched_domains,
            expanded_concepts,
            expansion_text,
        }
    }

    /// Projects query into dual-channel space:
    /// q_bridged = (1 - lambda) * q_symptom + lambda * q_hypothesis
    pub fn project_query(
        &self,
        query_text: &str,
        embedder: &RealTextEmbedder,
        lambda_weight: f32,
    ) -> (Vec<f32>, DiagnosticExpansion) {
        let expansion = self.expand(query_text);

        let v_symptom = embedder.embed(query_text);
        let v_hypothesis = embedder.embed(&expansion.expansion_text);

        let mut fused = vec![0.0f32; embedder.dim];
        for d in 0..embedder.dim {
            fused[d] = (1.0 - lambda_weight) * v_symptom[d] + lambda_weight * v_hypothesis[d];
        }

        (normalize(&fused), expansion)
    }
}
