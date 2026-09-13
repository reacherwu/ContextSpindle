PYTHON ?= python3
BENCHMARK_CONFIG := benchmarks/task-001-small.yaml
BENCHMARK_OUTPUT ?= experiments/results

.PHONY: benchmark-small benchmark-small-seed validate-experiment

# The protocol owns this canonical seed set; every invocation leaves an
# append-only record, including blocked/failed attempts.
benchmark-small:
	@set -e; for seed in 101 202 303; do \
		$(PYTHON) -m benchmarks.run_task_001 --config $(BENCHMARK_CONFIG) --output $(BENCHMARK_OUTPUT) --seed $$seed; \
	done

benchmark-small-seed:
	@test -n "$(SEED)" || (echo "Set SEED to a canonical seed (101, 202, or 303)." >&2; exit 2)
	$(PYTHON) -m benchmarks.run_task_001 --config $(BENCHMARK_CONFIG) --output $(BENCHMARK_OUTPUT) --seed $(SEED)

validate-experiment:
	@test -n "$(EXPERIMENT)" || (echo "Set EXPERIMENT to an experiment record directory." >&2; exit 2)
	$(PYTHON) -c 'from benchmarks.records import validate_record; validate_record("$(EXPERIMENT)")'
