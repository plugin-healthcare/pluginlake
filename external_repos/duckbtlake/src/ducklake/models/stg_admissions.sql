{{ config(materialized='table', schema='lake') }}

SELECT
    *,
    -- hospital_patient_admission composite key
    concat_ws('_',
              cast(hospital_id AS VARCHAR),
              cast(patient_id  AS VARCHAR),
              cast(admission_id AS VARCHAR)
    )            AS unique_admission_id,

    -- ICD-10 groupings
    regexp_extract(main_diagnosis_code,
                   '^([^./]+)',          -- take text before "." or "/"
                   1)                    AS icd10_category,
    substr(main_diagnosis_code, 1, 1)    AS icd10_chapter
FROM {{ source('lake_raw', 'admissions') }}
