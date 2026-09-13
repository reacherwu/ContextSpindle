# Architecture — v0.1 proposal

This is an initial, deliberately minimal proposal. It is not a validated architecture; changes to its mathematical core require an RFC and review.

```text
event -> encoder -> temporal state -> memory router
                                      |-> local state
                                      |-> sparse event memory
                                      |-> causal graph
                           -> memory judge -> write/read/forget/revise
```

## Event record

Each stored event will expose: `event_id`, `timestamp`, `embedding`, `importance`, `novelty`, `surprise`, `causal_score`, `retrieval_score`, `uncertainty`, and `metadata`.

## v0.1 interfaces

```python
model = Continuum(...)
state = model.reset()
output = model.step(event)
result = model.query(query)
model.revise(event_id, evidence)
```

## Temporal State (TASK-001)

A light gated recurrent state handles local dependencies only:

`h_t = (1 - gate_t) * h_(t-1) + gate_t * candidate_t`

where both gate and candidate are learned projections of the current input and prior state. Long-term storage is explicitly out of scope for TASK-001.

## Future modules

- Adaptive memory uses configurable, interpretable importance weights.
- Sparse memory uses time/importance filters plus cosine top-k candidates.
- The router starts rule-based and must be replaceable by a learned policy.
- Phase interaction is an ablatable learned-amplitude/phase score, not quantum computation.
- The causal graph represents hypotheses separately from validated causal relations.
- Revision appends provenance rather than overwriting history.
