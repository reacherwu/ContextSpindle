import unittest
import torch
from continuum.memory.cold_memory import ColdCandidateMemory

class TestColdMemory(unittest.TestCase):
    def setUp(self):
        self.capacity = 10
        self.emb_dim = 16
        self.state_dim = 8
        self.memory = ColdCandidateMemory(capacity=self.capacity, embedding_dim=self.emb_dim, state_dim=self.state_dim)

    def test_capacity_bound(self):
        for i in range(20):
            emb = torch.randn(self.emb_dim)
            state = torch.randn(self.state_dim)
            self.memory.archive(event_id=i, timestamp=float(i), embedding=emb, temporal_state=state, importance=0.5, provenance="test")
        
        self.assertEqual(len(self.memory.records), self.capacity)
        self.assertEqual(self.memory.embeddings_tensor.shape[0], self.capacity)

    def test_fifo_eviction(self):
        for i in range(15):
            emb = torch.randn(self.emb_dim)
            state = torch.randn(self.state_dim)
            self.memory.archive(event_id=i, timestamp=float(i), embedding=emb, temporal_state=state, importance=0.5, provenance="test")
        
        self.assertEqual(len(self.memory.records), 10)
        self.assertEqual(self.memory.records[0].event_id, 5)
        self.assertEqual(self.memory.records[-1].event_id, 14)

    def test_search_cosine_similarity(self):
        # Insert 3 records with specific embeddings
        e1 = torch.zeros(self.emb_dim); e1[0] = 1.0
        e2 = torch.zeros(self.emb_dim); e2[1] = 1.0
        e3 = torch.zeros(self.emb_dim); e3[2] = 1.0
        
        state = torch.randn(self.state_dim)
        
        self.memory.archive(event_id=1, timestamp=1.0, embedding=e1, temporal_state=state, importance=0.5, provenance="test")
        self.memory.archive(event_id=2, timestamp=2.0, embedding=e2, temporal_state=state, importance=0.5, provenance="test")
        self.memory.archive(event_id=3, timestamp=3.0, embedding=e3, temporal_state=state, importance=0.5, provenance="test")
        
        query = torch.zeros(self.emb_dim); query[1] = 1.0
        results = self.memory.search(query, top_k=2)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0].event_id, 2)
        self.assertAlmostEqual(results[0][1], 1.0, places=4)

    def test_remove(self):
        for i in range(5):
            emb = torch.randn(self.emb_dim)
            state = torch.randn(self.state_dim)
            self.memory.archive(event_id=i, timestamp=float(i), embedding=emb, temporal_state=state, importance=0.5, provenance="test")
        
        self.memory.remove(event_id=2)
        self.assertEqual(len(self.memory.records), 4)
        event_ids = [r.event_id for r in self.memory.records]
        self.assertNotIn(2, event_ids)
        self.assertEqual(self.memory.embeddings_tensor.shape[0], 4)

if __name__ == "__main__":
    unittest.main()
