# AeroForge-Agent

An offline-first multi-agent proof of concept for natural-language CFD workflows. It parses requirements, generates fallback STL geometry, prepares OpenFOAM dictionaries, runs optional solvers, and produces visual reports.

Run `pip install -e '.[dev]'`, then `python examples/demo_bmw_x3.py` and `pytest -q`. Without OpenFOAM the pipeline is an explicit dry-run, not a claim of physical accuracy.
