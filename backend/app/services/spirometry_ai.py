"""Spirometry analysis using Claude vision API (adapted from Medical Waves)."""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze this spirometry report image/PDF.
Extract the following values and return them in strict JSON format:
- fvc_actual: float
- fvc_predicted_pct: float
- fev1_actual: float
- fev1_predicted_pct: float
- fev1_fvc_ratio_actual: float (as a decimal or percentage)
- post_bd_fev1_actual: float or null
- post_bd_fvc_actual: float or null
- loop_morphology: string (one of: "Normal", "Scooped/Concave expiratory limb",
  "Witch's hat/Narrow", "Variable/Fixed upper airway obstruction", "Poor effort/Submaximal")
- fvc_best_two_diff_ml: float or null
- fev1_best_two_diff_ml: float or null
- back_extrapolated_volume_pct: float or null
- effort_quality: string or null
- number_of_acceptable_trials: integer or null
- early_termination: boolean or null

If a value is not found return null. Output raw JSON only — no markdown fences."""


def _clean_json(text: str) -> str:
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def extract_data_with_claude(image_path: str, api_key: str) -> Dict[str, Any]:
    """Extract spirometry values from an image using Claude vision."""
    import anthropic

    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf"}
    mime = mime_map.get(suffix, "image/jpeg")

    with open(image_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode()

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    content = response.content[0].text
    return json.loads(_clean_json(content))


def apply_diagnostic_logic(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Apply ATS/ERS spirometry diagnostic guidelines. Pure Python, no AI."""
    steps: List[Dict[str, str]] = []

    fvc_pct = data.get("fvc_predicted_pct")
    fev1_pct = data.get("fev1_predicted_pct")
    ratio = data.get("fev1_fvc_ratio_actual")
    if ratio and ratio > 1:
        ratio = ratio / 100

    is_obstructive = False
    if ratio is not None:
        if ratio < 0.70:
            is_obstructive = True
            steps.append({"Metric / Step": "FEV1/FVC Ratio", "Value / Observation": f"{ratio:.2f}",
                          "Diagnostic Interpretation": "Obstructive: FEV1/FVC < 0.70"})
        else:
            steps.append({"Metric / Step": "FEV1/FVC Ratio", "Value / Observation": f"{ratio:.2f}",
                          "Diagnostic Interpretation": "Normal: FEV1/FVC ≥ 0.70"})

    is_restrictive = False
    if fvc_pct is not None:
        if fvc_pct < 80:
            is_restrictive = True
            label = "Mixed pattern (Obstructive + Possible Restrictive)" if is_obstructive else "Restrictive pattern: FVC < 80%"
            steps.append({"Metric / Step": "FVC % Predicted", "Value / Observation": f"{fvc_pct}%",
                          "Diagnostic Interpretation": label})
        else:
            steps.append({"Metric / Step": "FVC % Predicted", "Value / Observation": f"{fvc_pct}%",
                          "Diagnostic Interpretation": "Normal: FVC ≥ 80%"})

    severity = "Normal"
    if fev1_pct is not None:
        if fev1_pct >= 70:
            severity = "Mild"
        elif 60 <= fev1_pct <= 69:
            severity = "Moderate"
        elif 50 <= fev1_pct <= 59:
            severity = "Moderately Severe"
        elif 35 <= fev1_pct <= 49:
            severity = "Severe"
        elif fev1_pct < 35:
            severity = "Very Severe"
        steps.append({"Metric / Step": "FEV1 % Predicted", "Value / Observation": f"{fev1_pct}%",
                      "Diagnostic Interpretation": f"Severity: {severity}"})

    morphology = data.get("loop_morphology")
    if morphology:
        steps.append({"Metric / Step": "Flow-Volume Loop", "Value / Observation": morphology,
                      "Diagnostic Interpretation": f"Visual pattern consistent with {morphology}"})

    post_fev1 = data.get("post_bd_fev1_actual")
    pre_fev1 = data.get("fev1_actual")
    if post_fev1 and pre_fev1:
        inc_ml = (post_fev1 - pre_fev1) * 1000
        inc_pct = (inc_ml / (pre_fev1 * 1000)) * 100
        rev = "Positive for reversibility" if (inc_pct >= 12 and inc_ml >= 200) else "Negative for reversibility"
        steps.append({"Metric / Step": "Reversibility", "Value / Observation": f"+{inc_ml:.0f}mL (+{inc_pct:.1f}%)",
                      "Diagnostic Interpretation": rev})

    compliance_issues: List[str] = []
    fvc_diff = data.get("fvc_best_two_diff_ml")
    if fvc_diff and fvc_diff > 150:
        compliance_issues.append(f"FVC variability {fvc_diff:.0f}mL (>150mL)")
    fev1_diff = data.get("fev1_best_two_diff_ml")
    if fev1_diff and fev1_diff > 150:
        compliance_issues.append(f"FEV1 variability {fev1_diff:.0f}mL (>150mL)")
    bev = data.get("back_extrapolated_volume_pct")
    if bev and bev > 5:
        compliance_issues.append(f"Back-extrapolated volume {bev:.1f}% (>5%)")
    effort = data.get("effort_quality")
    if effort and any(k in effort.lower() for k in ["poor", "sub-optimal", "suboptimal", "not reproducible", "unacceptable", "inadequate"]):
        compliance_issues.append(f"Technician note: {effort}")
    trials = data.get("number_of_acceptable_trials")
    if trials is not None and trials < 3:
        compliance_issues.append(f"Only {trials} acceptable trial(s) (<3 required)")
    if data.get("early_termination"):
        compliance_issues.append("Early termination detected (<6s expiration)")
    if morphology and "poor effort" in morphology.lower():
        compliance_issues.append("Flow-volume loop suggests submaximal effort")

    if compliance_issues:
        steps.append({"Metric / Step": "Patient Compliance", "Value / Observation": "; ".join(compliance_issues),
                      "Diagnostic Interpretation": "⚠️ Poor patient compliance — interpret with caution"})
    else:
        steps.append({"Metric / Step": "Patient Compliance", "Value / Observation": "Meets ATS/ERS criteria",
                      "Diagnostic Interpretation": "Acceptable quality"})

    final = severity
    if is_obstructive and is_restrictive:
        final += " Mixed Defect"
    elif is_obstructive:
        final += " Obstructive Defect"
    elif is_restrictive:
        final += " Restrictive Pattern"
    else:
        final = "Normal Spirometry"

    steps.append({"Metric / Step": "FINAL DIAGNOSIS", "Value / Observation": "—",
                  "Diagnostic Interpretation": final})
    return steps
