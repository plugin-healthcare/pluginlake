"""Core lineage sensor: sends OpenLineage events to Marquez after successful runs (ADR-007)."""

from dagster import (
    DagsterRunStatus,
    DefaultSensorStatus,
    Definitions,
    RunStatusSensorContext,
    run_status_sensor,
)

from pluginlake.core.lineage.config import LineageSettings
from pluginlake.core.lineage.openlineage_bridge import build_run_events, create_client, emit_run_events
from pluginlake.utils.logger import get_logger

logger = get_logger(__name__)


@run_status_sensor(
    name="openlineage_sensor",
    run_status=DagsterRunStatus.SUCCESS,
    default_status=DefaultSensorStatus.RUNNING,
    description="Sends an OpenLineage event per materialized asset to the configured lineage backend.",
)
def openlineage_sensor(context: RunStatusSensorContext) -> None:
    """Emit OpenLineage events for every asset materialized in a successful run."""
    if context.repository_def is None:
        logger.warning("No repository definition for run %s; skipping lineage.", context.dagster_run.run_id)
        return
    settings = LineageSettings()
    events = build_run_events(
        dagster_run=context.dagster_run,
        instance=context.instance,
        repository_def=context.repository_def,
        settings=settings,
    )
    if events:
        emit_run_events(create_client(settings), events)


def lineage_definitions(settings: LineageSettings | None = None) -> Definitions:
    """Return the lineage sensor when a lineage backend is configured, else nothing.

    Args:
        settings: Lineage settings; read from the environment when omitted.

    Returns:
        ``Definitions`` with ``openlineage_sensor``, or empty ``Definitions``.
    """
    settings = settings or LineageSettings()
    if not settings.enabled:
        return Definitions()
    logger.info("OpenLineage emission enabled, backend: %s", settings.url)
    return Definitions(sensors=[openlineage_sensor])
