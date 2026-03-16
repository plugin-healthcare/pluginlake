"""Upload Data — upload OMOP CSV, FHIR NDJSON, or generic files."""

import streamlit as st
from backend.ingestion import fetch_ingestion_runs
from client import ApiError, get_client
from components.ingestion_form import render_ingestion_runs

st.title("Upload Data")
st.caption("Upload data files to the datastation for processing.")

client = get_client()

# --- Upload tabs -----------------------------------------------------------

omop_tab, fhir_tab, generic_tab = st.tabs(["OMOP CSV", "FHIR NDJSON", "Generic Upload"])

with omop_tab:
    st.caption("Upload OMOP CDM tables as CSV files. Each file should correspond to one OMOP table.")
    with st.form("omop_upload", clear_on_submit=True):
        omop_file = st.file_uploader("Choose a CSV file", type=["csv"], key="omop_file")
        omop_table = st.text_input(
            "OMOP table name",
            placeholder="e.g. person, condition_occurrence, drug_exposure",
        )
        omop_submitted = st.form_submit_button("Upload OMOP CSV", type="primary")

    if omop_submitted and omop_file and omop_table:
        with st.spinner("Uploading..."):
            try:
                result = client.upload_omop_csv(omop_file.getvalue(), omop_file.name, omop_table)
                st.success(
                    f"Uploaded **{omop_file.name}** → `{omop_table}` (status: {result.get('status', 'unknown')})",
                    icon=":material/check_circle:",
                )
                if result.get("dagster_run_id"):
                    st.info(f"Dagster run: `{result['dagster_run_id']}`")
                fetch_ingestion_runs.clear()
            except ApiError as exc:
                st.error(f"Upload failed: {exc.detail}", icon=":material/error:")

with fhir_tab:
    st.caption("Upload FHIR R4 resources as NDJSON files. Each file should contain one resource type.")
    with st.form("fhir_upload", clear_on_submit=True):
        fhir_file = st.file_uploader("Choose an NDJSON file", type=["ndjson"], key="fhir_file")
        fhir_resource = st.selectbox(
            "FHIR resource type",
            options=[
                "patient",
                "encounter",
                "condition",
                "observation",
                "procedure",
                "medication_statement",
                "immunization",
                "allergy_intolerance",
            ],
        )
        fhir_submitted = st.form_submit_button("Upload FHIR NDJSON", type="primary")

    if fhir_submitted and fhir_file and fhir_resource:
        with st.spinner("Uploading..."):
            try:
                result = client.upload_fhir_ndjson(fhir_file.getvalue(), fhir_file.name, fhir_resource)
                st.success(
                    f"Uploaded **{fhir_file.name}** → `{fhir_resource}` (status: {result.get('status', 'unknown')})",
                    icon=":material/check_circle:",
                )
                if result.get("dagster_run_id"):
                    st.info(f"Dagster run: `{result['dagster_run_id']}`")
                fetch_ingestion_runs.clear()
            except ApiError as exc:
                st.error(f"Upload failed: {exc.detail}", icon=":material/error:")

with generic_tab:
    st.caption("Upload any supported file format for generic ingestion into the raw storage layer.")
    with st.form("generic_upload", clear_on_submit=True):
        gen_file = st.file_uploader(
            "Choose a file",
            type=["csv", "json", "parquet", "ndjson", "xlsx"],
            key="gen_file",
        )
        gen_dataset = st.text_input(
            "Dataset name",
            placeholder="e.g. custom_dataset",
        )
        gen_submitted = st.form_submit_button("Upload", type="primary")

    if gen_submitted and gen_file and gen_dataset:
        with st.spinner("Uploading..."):
            try:
                result = client.upload_file(gen_file.getvalue(), gen_file.name, gen_dataset)
                st.success(
                    f"Uploaded **{gen_file.name}** → `{gen_dataset}` (status: {result.get('status', 'unknown')})",
                    icon=":material/check_circle:",
                )
                if result.get("dagster_run_id"):
                    st.info(f"Dagster run: `{result['dagster_run_id']}`")
                fetch_ingestion_runs.clear()
            except ApiError as exc:
                st.error(f"Upload failed: {exc.detail}", icon=":material/error:")

# --- Recent runs -----------------------------------------------------------

st.header("Recent Ingestion Runs")
runs = fetch_ingestion_runs(client)
render_ingestion_runs(runs)
