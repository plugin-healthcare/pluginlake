{{ config(materialized='table', schema='lake') }}

SELECT
    *,
    concat_ws('_',
              cast(hospital_id AS VARCHAR),
              cast(patient_id  AS VARCHAR),
              cast(admission_id AS VARCHAR)
    )            AS unique_admission_id,

    regexp_extract(icd10_diagnosis_code, '^([^./]+)', 1) AS icd10_category,
    substr(icd10_diagnosis_code, 1, 1)                   AS icd10_chapter
FROM {{ source('lake_raw', 'diagnoses') }}