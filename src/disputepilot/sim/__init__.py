"""Simulation subpackage for synthetic dispute cases."""

from disputepilot.sim.generator import CaseGenerator, generate_cases
from disputepilot.sim.messy import MessyCaseGenerator, generate_messy_cases
from disputepilot.sim.rules import evaluate_winnability

__all__ = [
    "CaseGenerator",
    "MessyCaseGenerator",
    "evaluate_winnability",
    "generate_cases",
    "generate_messy_cases",
]
