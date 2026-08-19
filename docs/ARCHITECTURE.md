# Architecture

The orchestrator runs six deterministic stages. Pydantic models define the task/report contract. Tools are dependency-light and isolate OpenFOAM subprocesses. Missing OpenFOAM is represented as dry-run diagnostics rather than silently reported as converged CFD.

The current message bus is an in-process asyncio Queue suitable for a proof of concept. A distributed deployment can replace it without changing agent contracts.
