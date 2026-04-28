"""
Phase 13 — Configuration & Extensibility
========================================
Dynamic lookup of form templates based on version or document type.
"""

import logging
from typing import Dict, Any, List

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
                    }
                ]
            },
            "sdq_v1": {
                "id": "sdq_v1",
                "name": "Strengths and Difficulties Questionnaire (SDQ)",
                "fields": self._generate_sdq_fields()
            }
        }

    def _generate_sdq_fields(self) -> List[Dict[str, Any]]:
        labels = [
            "I try to be nice to other people. I care about their feelings.",
            "I am restless, I cannot stay still for long.",
            "I often complain of headaches, stomach-aches or sickness.",
            "I usually share with others (food, games, pens etc.)",
            "I get very angry and often lose my temper.",
            "I am rather solitary, I tend to play alone.",
            "I usually do as I am told.",
            "I worry a lot.",
            "I am helpful if someone is hurt, upset or feeling ill.",
            "I am constantly fidgeting or squirming.",
            "I have one good friend or more.",
            "I fight a lot. I can make other people do what I want.",
            "I am often unhappy, down-hearted or tearful.",
            "Other people my age generally like me.",
            "I am easily distracted, I find it difficult to concentrate.",
            "I am nervous in new situations. I easily lose confidence.",
            "I am kind to younger children.",
            "I am often accused of lying or cheating.",
            "Other children or young people pick on me or bully me.",
            "I often volunteer to help others (parents, teachers, other children).",
            "I think before I do things.",
            "I take things that are not mine from home, school or elsewhere.",
            "I get on better with adults than with other children.",
            "I have many fears, I am easily scared.",
            "I finish the work I'm doing. My attention is good."
        ]
        
        fields = []
        # Coordinates derived from OCR analysis of user's form
        y_start = 0.212
        y_step = 0.0255
        box_height = 0.022
        
        for i, label in enumerate(labels):
            q_id = f"q{i+1}"
            y1 = y_start + i * y_step
            y2 = y1 + box_height
            
            fields.append({
                "id": q_id,
                "name": label,
                "strategy": "radio_group",
                "priority": "critical",
                "type": "choice",
                "options": [
                    {"value": "Not True", "bbox_ratio": [0.65, y1, 0.75, y2]},
                    {"value": "Somewhat True", "bbox_ratio": [0.75, y1, 0.85, y2]},
                    {"value": "Certainly True", "bbox_ratio": [0.85, y1, 0.95, y2]}
                ]
            })
        return fields

    def get_template(self, template_id: str = "sdq_v1") -> Dict[str, Any]:
        """Phase 13: Look up template from registry. Defaults to sdq_v1 for current user."""
        template = self._registry.get(template_id)
        if not template:
            logger.warning(f"Template '{template_id}' not found. Falling back to default.")
            return self._registry["sdq_v1"]
        return template

_template_service = None

def get_template_service() -> TemplateService:
    global _template_service
    if _template_service is None:
        _template_service = TemplateService()
    return _template_service
