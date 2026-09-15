import unittest
from continuum.reasoning.semantic_bridge import SemanticCausalBridge
from benchmarks.reality_test.embedder import RealTextEmbedder


class TestSemanticCausalBridge(unittest.TestCase):
    def setUp(self):
        self.bridge = SemanticCausalBridge()
        self.embedder = RealTextEmbedder(32)

    def test_expansion_tls(self):
        query = "Agent failure: integration test failed with TLS handshake failure SSLV3_ALERT_HANDSHAKE_FAILURE"
        expansion = self.bridge.expand(query)
        self.assertIn("tls_crypto_configuration", expansion.matched_domains)
        self.assertIn("openssl", expansion.expanded_concepts)
        self.assertIn("crypto", expansion.expanded_concepts)

    def test_expansion_database(self):
        query = "504 Gateway Timeout in checkout service: connection pool exhausted"
        expansion = self.bridge.expand(query)
        self.assertIn("database_resource_limits", expansion.matched_domains)
        self.assertIn("db_connection_pool_size", expansion.expanded_concepts)

    def test_project_query_shape_and_norm(self):
        query = "SSLV3_ALERT_HANDSHAKE_FAILURE during mutual auth"
        v_bridged, exp = self.bridge.project_query(query, self.embedder, lambda_weight=0.5)
        self.assertEqual(v_bridged.shape[0], 32)
        norm = float(v_bridged.norm().item())
        self.assertAlmostEqual(norm, 1.0, places=4)


if __name__ == "__main__":
    unittest.main()
