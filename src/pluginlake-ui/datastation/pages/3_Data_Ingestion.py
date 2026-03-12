"""Data Ingestion page — upload files and monitor ingestion status."""

import streamlit as st
from backend.ingestion import fetch_ingestion_runs, upload_file
from client import ApiClient, ApiError
from components.ingestion_form import render_ingestion_runs, render_upload_form
from components.status import error_message

st.title("Data Ingestion")
st.caption("Upload data files and monitor ingestion pipeline status.")

client = ApiClient()

# --- Upload ----------------------------------------------------------------

st.header("Upload File")

uploaded_file, dataset = render_upload_form()

if uploaded_file is not None and dataset:
    with st.spinner("Uploading..."):
        try:
            result = upload_file(client, uploaded_file.getvalue(), uploaded_file.name, dataset)
            st.success(
                f"Uploaded **{result.get('filename', uploaded_file.name)}** "
                f"→ dataset `{dataset}` "
                f"(status: {result.get('status', 'unknown')})",
                icon=":material/check_circle:",
            )
            if result.get("dagster_run_id"):
                st.info(f"Dagster run: `{result['dagster_run_id']}`")
            # Clear run cache so the new run shows up
            fetch_ingestion_runs.clear()
        except ApiError as exc:
            error_message(f"Upload failed: {exc.detail}")

# --- Ingestion runs --------------------------------------------------------

st.header("Recent Ingestion Runs")

runs = fetch_ingestion_runs(client)
render_ingestion_runs(runs)
