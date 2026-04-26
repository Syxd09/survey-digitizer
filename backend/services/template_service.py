"""
Phase 13 — Configuration & Extensibility
========================================
Dynamic lookup of form templates based on version or document type.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TemplateService:
    def __init__(self):
        # In a production system, these would be loaded from a DB or YAML files.
        self._registry = {
            "default_survey_v1": {
                "id": "default_survey_v1",
                "name": "Standard Survey Form",
                "fields": [
                    {
                        "id": "survey_id", 
                        "strategy": "line_search", 
                        "regex": r"Survey\s*ID[:\s]*(\w+)", 
                        "priority": "critical",
                        "type": "text"
                    },
                    {
                        "id": "completion_date", 
                        "strategy": "anchor", 
                        "anchor_texts": ["Date:", "Date of Completion:"], 
                        "search_direction": "right", 
                        "priority": "important",
                        "type": "date"
                    },
                    {
                        "id": "respondent_email",
                        "strategy": "anchor",
                        "anchor_text": "Email:",
                        "search_direction": "right",
                        "priority": "important",
                        "type": "email"
                    },
                    {
                        "id": "satisfaction_score",
                        "strategy": "zone",
                        "bbox_ratio": [0.1, 0.4, 0.2, 0.45], # Example zone
                        "priority": "important",
                        "type": "numeric",
                        "min": 1,
                        "max": 5
                    },
                    {
                        "id": "newsletter_opt_in",
                        "strategy": "zone",
                        "type": "checkbox",
                        "bbox_ratio": [0.1, 0.5, 0.12, 0.53],
                        "priority": "optional"
                    }
                ]
            }
        }

    def get_template(self, template_id: str = "default_survey_v1") -> Dict[str, Any]:
        """Phase 13: Look up template from registry."""
        template = self._registry.get(template_id)
        if not template:
            logger.warning(f"Template '{template_id}' not found. Falling back to default.")
            return self._registry["default_survey_v1"]
        return template

_template_service = None

def get_template_service() -> TemplateService:
    global _template_service
    if _template_service is None:
        _template_service = TemplateService()
    return _template_service
