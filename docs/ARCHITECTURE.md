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

TASK-001 introduces one deliberately small, local recurrent component.  Its
normative contract is defined in
[RFC-0001](../.agent/proposals/RFC-0001-temporal-state.md); this section is a
summary, not a second definition.

The component consumes an already encoded event vector and a caller-owned
state.  It emits the next state and diagnostic gate/candidate tensors.  It
does not store events, interpret timestamps, retrieve history, make causal
claims, or reset itself.

```python
config = TemporalStateConfig(input_size=D, hidden_size=H)
state = temporal_state.initial_state(batch_size=B, device=x.device, dtype=x.dtype)
transition = temporal_state.step(x_t, state)
next_state = transition.state

states, final_state = temporal_state.forward_sequence(x, initial_state=None)
```

The input to `step` is a finite rank-2 tensor `[B, D]`; the incoming and
returned state is a finite rank-2 tensor `[B, H]`. `forward_sequence` consumes
`[B, T, D]` strictly from `t=0` through `t=T-1` and returns `[B, T, H]` plus the
same state that the corresponding repeated `step` calls would produce. A reset
is represented only by `initial_state`, whose required default is all zeros.

For each batch row and hidden coordinate:

`g_t = sigmoid(W_g x_t + U_g h_(t-1) + b_g)`

`c_t = tanh(W_c x_t + U_c h_(t-1) + b_c)`

`h_t = (1 - g_t) * h_(t-1) + g_t * c_t`

The gate is element-wise, and `W_*`, `U_*`, and `b_*` are the only trainable
parameters in this component. With finite inputs and state, the implementation
must reject non-finite values; with the zero initialization, every coordinate
of the mathematical state remains in `[-1, 1]`. Long-term storage remains
explicitly out of scope.

## Future modules

- Adaptive memory uses configurable, interpretable importance weights.
- Sparse memory uses time/importance filters plus cosine top-k candidates.
- The router starts rule-based and must be replaceable by a learned policy.
- Phase interaction is an ablatable learned-amplitude/phase score, not quantum computation.
- The causal graph represents hypotheses separately from validated causal relations.
- Revision appends provenance rather than overwriting history.
