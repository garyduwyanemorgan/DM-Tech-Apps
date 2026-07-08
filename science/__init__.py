"""Lagoon Intelligence Platform — Scientific Engine layer (v2).

Pure-Python, explainable decision-support engines that sit alongside the
existing `core/` compliance logic. They are NOT a replacement — `core/`
remains the Production Foundation v1 compliance/alert system. These engines
add the scientific reasoning chain described in science/CONTEXT.md:

    Nutrient Sources → Hydraulic Transport → Sediment Interactions
        → Fe-P Coupling → Bloom Formation → Operational Risk

Design rules (science/Architecture.md):
  - Pure Python, zero UI dependencies
  - Explainable: every result carries the reasoning that produced it
  - No hard-coded thresholds: all parameters live in science/config.py
  - No hidden AI decisions: models are transparent and parametric

Engines:
  nutrient_sources  — attribute nutrient load to TSE / internal / runoff /
                      groundwater / atmospheric sources
  sediment_loading  — Fe-P redox internal phosphorus release risk
  residence_time    — hydraulic residence time + flushing efficiency
  bloom_forecast    — bloom probability / severity / recovery time
  community         — favoured algae group / type + ecological succession stage,
                      anchored by the measured phycocyanin:chlorophyll ratio;
                      recommends a confirmatory lab test when cyano-favoured
  digital_twin      — what-if scenario simulation over the chain
"""

__version__ = "2.0.0"
