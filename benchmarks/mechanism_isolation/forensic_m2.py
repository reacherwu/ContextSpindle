import torch
import random
from benchmarks.mechanism_isolation.m2_retrieval import *

for s in [101, 202, 303]:
    res = run_m2_experiment("10", 500, s)
    print(f"Seed {s}: root_rank={res['root_rank']}, root_in_top_k={res['root_in_top_k']}, root_score={res['root_score']}, best_decoy_score={res['best_decoy_score']}")
