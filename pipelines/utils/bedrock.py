"""
AWS Bedrock utility — NLP extraction and DCI computation.
Uses Claude Haiku 4.5 for fast/cheap extraction, Sonnet for complex reasoning.
"""

import json
import os
import re
import boto3
from typing import Any

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# Inference profile IDs — Claude 4.x requires cross-region inference profiles (us. prefix)
# Haiku 4.5 used for both tasks — Sonnet 3.7 requires additional Marketplace subscription
HAIKU_MODEL  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"   # NLP extraction
SONNET_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"   # DCI computation (Haiku 4.5 capable for structured JSON)

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=REGION)
    return _client


def invoke(model_id: str, prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """Invoke a Bedrock Claude model and return the text response."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = _get_client().invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["content"][0]["text"]


def extract_json(text: str) -> dict | None:
    """Extract the first JSON object from a model response."""
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


# ── Disease event extraction from unstructured text ──────────────────────

EXTRACTION_PROMPT = """You are an epidemiological data extractor. Extract structured fields from this disease outbreak report.
Return ONLY valid JSON — no commentary, no markdown fences.

Required fields:
{{
  "disease": "disease name (e.g. Dengue, Ebola, Cholera)",
  "event_type": "one of: arbovirus | hemorrhagic | bacterial | respiratory | parasitic | conflict | other",
  "country": "country name",
  "country_iso3": "ISO 3166-1 alpha-3 code (3 uppercase letters)",
  "admin1": "subnational region/province, or empty string",
  "cases_reported": integer or null,
  "deaths_reported": integer or null,
  "start_date": "YYYY-MM-DD or empty string",
  "severity": float 0.0-1.0 (0=minimal, 1=catastrophic),
  "overlap_with_malaria_zone": float 0.0-1.0 (probability this location is malaria-endemic),
  "narrative": "1-2 sentence factual summary"
}}

Report text:
{text}"""


def extract_disease_event(text: str) -> dict:
    """
    Use Claude Haiku to extract structured epidemiological fields from raw report text.
    Returns a dict with the extracted fields, or {} on failure.
    """
    prompt = EXTRACTION_PROMPT.format(text=text[:4000])
    try:
        response = invoke(HAIKU_MODEL, prompt, max_tokens=512)
        result = extract_json(response)
        return result or {}
    except Exception as e:
        print(f"    Bedrock extraction error: {e}")
        return {}


# ── DCI (Diagnostic Confusion Index) computation ─────────────────────────

DCI_PROMPT = """You are a malaria epidemiologist computing Diagnostic Confusion Index (DCI) scores.

DCI measures the probability that a concurrent febrile outbreak in a country will cause malaria cases
to be misattributed to the co-circulating pathogen, leading to delayed or missed malaria diagnosis.

Inputs:
- Country: {country} ({iso3})
- Malaria endemicity: {malaria_incidence} cases per 1,000 population at risk
- Concurrent outbreak: {disease} ({event_type})
- Outbreak severity: {severity}/1.0
- Symptoms overlap with malaria: {symptom_overlap}
- Geographic overlap with malaria zones: {geo_overlap}

DCI scoring:
- 0.0-0.2: Negligible — outbreak unlikely to cause malaria misdiagnosis
- 0.2-0.4: Low — minor diagnostic interference possible
- 0.4-0.6: Moderate — meaningful confusion risk, enhanced surveillance needed
- 0.6-0.8: High — significant misdiagnosis risk, active case-finding required
- 0.8-1.0: Critical — severe overlap, expect malaria cases misattributed to co-pathogen

Return ONLY valid JSON: {{"dci_score": float, "reasoning": "one sentence"}}"""


def compute_dci(
    country: str,
    iso3: str,
    malaria_incidence: float,
    disease: str,
    event_type: str,
    severity: float,
    geo_overlap: float,
) -> dict:
    """
    Compute DCI score for an outbreak event using Claude Sonnet.
    Returns {"dci_score": float, "reasoning": str}.
    """
    # Symptom overlap heuristic by disease type
    SYMPTOM_OVERLAPS = {
        "arbovirus": "High — dengue/chikungunya/Zika all present with fever, myalgia, and thrombocytopenia identical to malaria",
        "hemorrhagic": "Moderate — VHFs share fever but hemorrhagic features distinguish them",
        "respiratory": "Low — respiratory focus differs from malaria's fever+anaemia pattern",
        "bacterial": "Moderate — typhoid and bacterial meningitis share fever but distinct clinical features",
        "parasitic": "High — other parasitic febrile illnesses overlap strongly",
        "conflict": "Low — conflict disrupts care access but doesn't directly create diagnostic confusion",
    }
    symptom_overlap = SYMPTOM_OVERLAPS.get(event_type, "Unknown")

    prompt = DCI_PROMPT.format(
        country=country,
        iso3=iso3,
        malaria_incidence=malaria_incidence,
        disease=disease,
        event_type=event_type,
        severity=severity,
        symptom_overlap=symptom_overlap,
        geo_overlap=geo_overlap,
    )
    try:
        response = invoke(SONNET_MODEL, prompt, max_tokens=256)
        result = extract_json(response)
        if result and "dci_score" in result:
            result["dci_score"] = max(0.0, min(1.0, float(result["dci_score"])))
            return result
    except Exception as e:
        print(f"    DCI computation error: {e}")
    return {"dci_score": None, "reasoning": "computation failed"}
