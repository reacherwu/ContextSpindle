import torch
from torch import Tensor
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ColdCandidateRecord:
    event_id: int
    timestamp: float
    compressed_embedding: Tensor  # Shape: [D], float32, normalized
    state_fingerprint: Tensor     # Shape: [H], state snapshot at eviction
    importance_at_eviction: float  # I_t when evicted
    provenance_summary: str       # Brief trace of why it was initially kept/evicted

class ColdCandidateMemory:
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int):
        self.capacity = capacity
        self.embedding_dim = embedding_dim
        self.state_dim = state_dim
        
        # Bounded FIFO buffer for compressed evicted records
        self.records: list[ColdCandidateRecord] = []
        self.embeddings_tensor: Tensor | None = None
        
    def archive(self, event_id: int, timestamp: float, embedding: Tensor, 
                temporal_state: Tensor, importance: float, provenance: str) -> ColdCandidateRecord:
        # Store compressed version of evicted event
        
        emb = embedding.detach().float()
        if emb.ndim > 1:
            emb = emb.squeeze()
        norm = torch.norm(emb, p=2)
        if norm > 1e-8:
            emb = emb / norm
            
        state_fingerprint = temporal_state.detach().float()
        
        record = ColdCandidateRecord(
            event_id=event_id,
            timestamp=timestamp,
            compressed_embedding=emb,  # No dimensionality reduction yet - future optimization
            state_fingerprint=state_fingerprint,
            importance_at_eviction=importance,
            provenance_summary=provenance
        )
        
        # If at capacity, FIFO evict oldest cold candidate
        if len(self.records) >= self.capacity:
            self._evict_oldest()
            
        self.records.append(record)
        
        new_emb = emb.unsqueeze(0)
        if self.embeddings_tensor is None:
            self.embeddings_tensor = new_emb
        else:
            self.embeddings_tensor = torch.cat([self.embeddings_tensor, new_emb], dim=0)
            
        return record
        
    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        self.records.pop(0)
        if self.embeddings_tensor is not None:
            if len(self.records) == 0:
                self.embeddings_tensor = None
            else:
                self.embeddings_tensor = self.embeddings_tensor[1:]
                
    def search(self, query_embedding: Tensor, top_k: int = 10) -> list[tuple[ColdCandidateRecord, float]]:
        # Cosine similarity search over cold candidates
        if len(self.records) == 0 or self.embeddings_tensor is None:
            return []
            
        q = query_embedding.detach().float()
        if q.ndim > 1:
            q = q.squeeze()
        q_norm = torch.norm(q, p=2)
        if q_norm > 1e-8:
            q = q / q_norm
            
        k = min(top_k, len(self.records))
        with torch.no_grad():
            sims = torch.mv(self.embeddings_tensor, q)
            top_vals, top_indices = torch.topk(sims, k=k)
            
        results: list[tuple[ColdCandidateRecord, float]] = []
        for sim_val, idx in zip(top_vals.tolist(), top_indices.tolist()):
            results.append((self.records[idx], float(sim_val)))
            
        return results
        
    def remove(self, event_id: int) -> None:
        # Remove a candidate that was restored to hot memory
        idx_to_remove = -1
        for i, rec in enumerate(self.records):
            if rec.event_id == event_id:
                idx_to_remove = i
                break
                
        if idx_to_remove != -1:
            self.records.pop(idx_to_remove)
            if self.embeddings_tensor is not None:
                if len(self.records) == 0:
                    self.embeddings_tensor = None
                else:
                    self.embeddings_tensor = torch.cat(
                        [self.embeddings_tensor[:idx_to_remove], self.embeddings_tensor[idx_to_remove + 1:]], dim=0
                    )
                    
    def get_stats(self) -> dict[str, Any]:
        return {
            "capacity": self.capacity,
            "current_size": len(self.records),
            "embedding_dim": self.embedding_dim,
            "state_dim": self.state_dim,
        }


class DiversifiedDynamicsColdMemory(ColdCandidateMemory):
    """
    Subspace-Diversified Attractor Cold Memory.
    Evicts the most redundant candidate (highest cosine similarity to another record in memory)
    when maximum redundancy exceeds sim_thresh, protecting unique causal attractors from being
    evicted by repetitive routine chatter or alert storms.
    """
    def __init__(self, capacity: int, embedding_dim: int, state_dim: int, sim_thresh: float = 0.65):
        super().__init__(capacity=capacity, embedding_dim=embedding_dim, state_dim=state_dim)
        self.sim_thresh = sim_thresh

    def _evict_oldest(self) -> None:
        if len(self.records) == 0:
            return
        evict_idx = -1
        with torch.no_grad():
            if self.embeddings_tensor is not None and len(self.records) > 1:
                sim_mat = torch.matmul(self.embeddings_tensor, self.embeddings_tensor.T)
                sim_mat.fill_diagonal_(-1.0)
                max_sims, _ = torch.max(sim_mat, dim=1)
                redundant_mask = max_sims >= self.sim_thresh
                if redundant_mask.any():
                    # Evict the candidate with the highest mutual redundancy
                    evict_idx = int(max_sims.argmax().item())
        if evict_idx == -1:
            # If no candidate exceeds redundancy threshold, evict by lowest importance/state norm
            scores = []
            for r in self.records:
                st_norm = float(torch.norm(r.state_fingerprint, p=2).item())
                scores.append(0.4 * r.importance_at_eviction + 0.6 * st_norm)
            evict_idx = int(torch.tensor(scores).argmin().item())

        self.records.pop(evict_idx)
        if len(self.records) == 0:
            self.embeddings_tensor = None
        else:
            self.embeddings_tensor = torch.cat(
                [self.embeddings_tensor[:evict_idx], self.embeddings_tensor[evict_idx + 1:]], dim=0
            )

