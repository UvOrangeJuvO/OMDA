"""Pure Recommendation Core (G2).

Deterministic, dependency-free selection rules. This package MUST NOT import or
call storage, network, browser, vendor SDKs or any external Port. The
Orchestrator reads immutable history snapshots and passes them in as arguments
(SPEC §3.1, §3.3; Master Plan §4).
"""
