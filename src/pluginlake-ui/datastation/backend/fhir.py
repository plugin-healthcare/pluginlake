"""Backend logic for the FHIR page."""

import logging
from typing import Any

import streamlit as st
from client import ApiClient, ApiError

logger = logging.getLogger(__name__)

FHIR_RESOURCE_TYPES = [
    "patient",
    "encounter",
    "condition",
    "observation",
    "procedure",
    "medication_statement",
    "immunization",
    "allergy_intolerance",
]

FHIR_TO_OMOP_MAPPING = {
    "patient": {"omop_table": "person", "description": "Demographics and patient identity"},
    "encounter": {"omop_table": "visit_occurrence", "description": "Hospital visits and encounters"},
    "condition": {"omop_table": "condition_occurrence", "description": "Diagnoses and conditions"},
    "observation": {"omop_table": "observation", "description": "Lab results, vital signs, social history"},
    "procedure": {"omop_table": "procedure_occurrence", "description": "Surgical and clinical procedures"},
    "medication_statement": {
        "omop_table": "drug_exposure",
        "description": "Medication prescriptions and administrations",
    },
    "immunization": {"omop_table": "drug_exposure", "description": "Vaccination records"},
    "allergy_intolerance": {"omop_table": "observation", "description": "Allergy and intolerance records"},
}


@st.cache_data(ttl=120, show_spinner="Loading FHIR statistics...")
def fetch_fhir_statistics(_client: ApiClient) -> dict[str, Any]:
    """Fetch aggregated FHIR statistics from the API."""
    try:
        return _client.get_fhir_statistics()
    except ApiError:
        logger.exception("Failed to fetch FHIR statistics")
        return {}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_fhir_tables(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch FHIR raw tables from the catalog."""
    try:
        return _client.get_catalog_tables(schema="fhir_raw")
    except ApiError:
        logger.exception("Failed to fetch FHIR raw tables")
        return []


@st.cache_data(ttl=60, show_spinner=False)
def fetch_fhir_omop_tables(_client: ApiClient) -> list[dict[str, Any]]:
    """Fetch FHIR-to-OMOP translated tables from the catalog."""
    try:
        return _client.get_catalog_tables(schema="fhir_omop_raw")
    except ApiError:
        logger.exception("Failed to fetch FHIR-OMOP tables")
        return []
