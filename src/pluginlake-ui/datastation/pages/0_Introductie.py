"""Introductie -- hoe werkt het pluginlake platform."""

from pathlib import Path

import streamlit as st

from config import get_settings

settings = get_settings()

st.title("PLUGIN-Lake Datastation dashboard")

st.markdown(f"""
Dit dashboard geeft inzicht in de data van het datastation **{settings.datastation_name}** (`{settings.datastation_id}`).
Hieronder wordt kort toegelicht hoe het platform werkt en hoe het dashboard is opgebouwd.
""")

# -- Architectuuroverzicht ----------------------------------------------------
overview_dagster = Path(settings.assets_dir) / "components-f6b7b1846953643053de87560a4a6583.png"
asset_dagster = Path(settings.assets_dir) / "overview-1-d0d3b466c2dad7a064e9a6684aa4d8b4.png"

# -- Uitleg -------------------------------------------------------------------

st.subheader("Data orchestratie met Dagster")

st.markdown("""
Pluginlake is gebouwd op [Dagster](https://dagster.io), een open-source data orchestrator.
Het platform bestaat uit de volgende bouwstenen:

- **Assets** vormen de kern van het platform. Een asset representeert een entiteit in het dataplatform
  (bijv. een tabel met patienten of diagnoses) en de code die deze data produceert.
  De afhankelijkheden tussen assets vormen samen de *lineage* van het project.
""")

if not asset_dagster.exists():
    st.info("Asset diagram not found.", icon=":material/info:")

col_text, col_img = st.columns([3, 1])

col_text.markdown("""
- **Definitions** groeperen alle assets, schedules en checks binnen een project.
  Zij vormen de container waarbinnen alles samenkomt.

- **Resources** zijn de externe systemen waar assets gebruik van maken, zoals de database (DuckLake) waar data wordt opgeslagen.

- **Schedules** en **Asset Checks** zorgen ervoor dat assets automatisch worden bijgewerkt en gevalideerd.

Elke aanlevering van data via de API wordt herkend als een asset en triggert automatisch de bijbehorende verwerkingsstappen. Dit proces wordt binnen Dagster *materialisatie* genoemd en maakt het mogelijk om data pipelines volledig geautomatiseerd en datagedreven te laten werken.
""")

if asset_dagster.exists():
    col_img.image(str(asset_dagster), caption="Definition - Asset relationship", use_container_width=True)

if overview_dagster.exists():
    st.image(str(overview_dagster), caption="Dagster overview", width=600)
else:
    st.info("Overview diagram not found.", icon=":material/info:")

st.subheader("Dashboard overzicht")

st.markdown("""
| Pagina | Inhoud |
|---|---|
| **Data Catalog** | Overzicht van alle assets en bijbehorende data |
| **Pipelines** | Status van verwerkingsruns en materialisaties |
| **OMOP** | Statistieken over klinische data (OMOP CDM) |
| **FHIR** | Overzicht van beschikbare FHIR resources |
| **Upload Data** | Data uploaden naar het datastation |
""")

st.divider()

st.caption(
    "Meer weten over hoe Dagster werkt? "
    "Bekijk de [Dagster basics tutorial](https://docs.dagster.io/dagster-basics-tutorial)."
)
