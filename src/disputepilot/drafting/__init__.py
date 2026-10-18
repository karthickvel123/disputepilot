"""DisputePilot Rebuttal Drafting and Verification Module."""

from disputepilot.drafting.drafter import DraftSentence, RebuttalDraft, RebuttalDrafter
from disputepilot.drafting.facts import Fact, FactSet, build_fact_set
from disputepilot.drafting.verifier import (
    StrippedSentence,
    VerifierReport,
    verify_rebuttal,
    verify_sentence,
)

__all__ = [
    "DraftSentence",
    "Fact",
    "FactSet",
    "RebuttalDraft",
    "RebuttalDrafter",
    "StrippedSentence",
    "VerifierReport",
    "build_fact_set",
    "verify_rebuttal",
    "verify_sentence",
]
