"""Admissions domain services."""

from .eligibility_check import EligibilityResult, check_age_eligibility

__all__ = ["EligibilityResult", "check_age_eligibility"]