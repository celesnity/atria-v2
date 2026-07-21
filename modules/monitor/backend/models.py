"""Typed Monitor connector output contracts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MonitorModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class OperationalSnapshotResult(MonitorModel):
    contract_version: str
    generated_at: str | None = None
    simulation_minute: int = 0
    scenario: str | None = None
    run_id: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    work_context: dict[str, Any] = Field(default_factory=dict)
    source_health: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    intake: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)


class EventTimelineResult(MonitorModel):
    contract_version: str
    simulation_minute: int = 0
    scenario: str | None = None
    run_id: str | None = None
    latest_seq: int = 0
    events: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceResult(MonitorModel):
    event: dict[str, Any] | None = None
    observations: list[dict[str, Any]] = Field(default_factory=list)
    source_health: dict[str, Any] = Field(default_factory=dict)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class SourceHealthResult(MonitorModel):
    contract_version: str
    generated_at: str | None = None
    overall_status: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    data_health: str


class ProduceDataProductResult(MonitorModel):
    contract_version: str
    generated_at: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    work_context: dict[str, Any] = Field(default_factory=dict)
    equipment_state: dict[str, Any] = Field(default_factory=dict)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    intake: dict[str, Any] = Field(default_factory=dict)
    downtime_candidates: list[dict[str, Any]] = Field(default_factory=list)
    cycle_events: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[dict[str, Any]] = Field(default_factory=list)
    source_health: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class OptimizeDataProductResult(MonitorModel):
    contract_version: str
    generated_at: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    work_context: dict[str, Any] = Field(default_factory=dict)
    operational_state_snapshot: dict[str, Any] = Field(default_factory=dict)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    intake: dict[str, Any] = Field(default_factory=dict)
    production_loss_events: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_invalidating_events: list[dict[str, Any]] = Field(default_factory=list)
    intervention_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    data_readiness: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
