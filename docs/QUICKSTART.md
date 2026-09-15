# Continuum v0.1 Quickstart Guide

Get started with Continuum in under 3 minutes.

## 1. Installation

Continuum requires Python 3.10+ and PyTorch:

```bash
git clone https://github.com/continuum-engine/continuum.git
cd continuum
pip install -e .
```

---

## 2. Minimal Example

```python
import torch
from continuum import ContinuumEngine, ContinuumConfig

# 1. Initialize Engine with bounded 750 memory slots
config = ContinuumConfig(
    embedding_dim=32,
    state_dim=32,
    hot_capacity=250,
    cold_capacity=500,
)
engine = ContinuumEngine(config)

# 2. Ingest streaming telemetry events in O(1) time
for step in range(1000):
    x_t = torch.randn(32)
    result = engine.step(x_t, payload_ref=f"device_telemetry_{step}")

print(f"Ingested 1000 events. Total slots used: {engine.get_stats()['total_slots']} / 750 (Strictly Bounded)")

# 3. Query retrospective root causes when an incident occurs
incident_symptom = torch.randn(32)
candidates = engine.query(incident_symptom, top_k=3)

for rank, match in enumerate(candidates, 1):
    print(f"Candidate #{rank}: Event ID={match.event_id}, Score={match.revision_score:.4f}, Tag={match.provenance}")
```

---

## 3. Command Line Interface

```bash
# Check runtime status
python3 -m continuum.cli status

# Run the live streaming demo
python3 -m continuum.cli demo
```

---

## 4. Running the Tests

```bash
python3 -m unittest discover -s tests -v
```
