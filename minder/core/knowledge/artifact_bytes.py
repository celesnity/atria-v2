"""Resolve an artifact id to an on-disk file path for ingestion."""

from __future__ import annotations


def artifact_path(artifact_id: int) -> str:
    """Return the absolute path of an uploaded artifact's file.

    Reuses ArtifactService's resolution so knowledge ingest reads the exact
    bytes the upload stored.

    Note: ArtifactService has no sync path-resolution method. On-disk path
    resolution requires an async DB lookup (_resolve_working_dir) plus
    _resolve_artifact_file, both of which need a live sessionmaker. This
    function raises NotImplementedError until a sync accessor or DI hook is
    wired here. Artifact ingest is verified in integration, not in the unit
    test suite.
    """
    raise NotImplementedError(
        f"artifact_path({artifact_id!r}): ArtifactService exposes only async resolution "
        "(_resolve_working_dir + _resolve_artifact_file). Wire a sessionmaker or a "
        "sync accessor (e.g. ArtifactService.resolve_path_sync) to implement this."
    )
