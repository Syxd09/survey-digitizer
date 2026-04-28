"""
Phase 8 — Decision Engine
=========================
Determines the final status of a processed form and routes it to 
auto-acceptance or manual review.
"""

import logging
from typing import List, Dict, Any

from config import settings

logger = logging.getLogger(__name__)

class DecisionEngine:
    """Implements Phase 8: Final routing logic."""

    def __init__(self, confidence_threshold: float = None):
        self.confidence_threshold = confidence_threshold or settings.AUTO_ACCEPT_THRESHOLD

    def decide(self, field_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Determines form status based on field-level outcomes and priorities.
        
        Rules:
        - REJECT: Any CRITICAL field fails OR any Hard Error.
        - NEEDS_REVIEW: Any Important field fails OR any field < threshold.
        - AUTO_ACCEPT: All Critical/Important fields pass with high confidence.
        """
        if not field_results:
            return {"status": "ERROR", "reason": "No fields processed"}

        hard_errors = []
        soft_errors = []
        low_confidence_fields = []
        critical_failures = []
        
        total_conf = 0.0
        
        for field in field_results:
            f_id = field.get("id")
            conf = field.get("confidence", 0.0)
            status = field.get("status")
            priority = field.get("priority", "important").lower() # critical, important, optional
            
            total_conf += conf
            
            if status == "REJECT":
                hard_errors.append(f_id)
                if priority == "critical":
                    critical_failures.append(f_id)
            elif status == "NEEDS_REVIEW":
                soft_errors.append(f_id)
                
            if conf < self.confidence_threshold:
                low_confidence_fields.append(f_id)

        avg_conf = total_conf / len(field_results)
        
        final_status = "AUTO_ACCEPT"
        reason = "All validation passed with high confidence."

        if critical_failures or hard_errors:
            final_status = "REJECT"
            issues = []
            if critical_failures:
                issues.append(f"Critical field failures: {', '.join(critical_failures)}")
            if hard_errors:
                issues.append(f"Hard validation errors: {', '.join(hard_errors)}")
            reason = "; ".join(issues)
            
        elif soft_errors or low_confidence_fields:
            final_status = "NEEDS_REVIEW"
            issues = []
            if soft_errors:
                issues.append(f"Soft errors in: {', '.join(soft_errors)}")
            if low_confidence_fields:
                issues.append(f"Low confidence in: {', '.join(low_confidence_fields)}")
            reason = "; ".join(issues)

        return {
            "status": final_status,
            "overall_confidence": round(avg_conf, 4),
            "reason": reason,
            "hard_errors": hard_errors,
            "soft_errors": soft_errors,
            "low_confidence_fields": low_confidence_fields,
            "critical_failures": critical_failures
        }

def get_decision_engine() -> DecisionEngine:
    return DecisionEngine()
