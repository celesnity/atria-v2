// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import Dashboard from "./dashboard";
import { TABS } from "./dashboard.tabs";

let simulatorOffline = false;

const assets = [
  { id: "washer-1", asset_tag: "WASH-01", type: "washer", status: "running", mode: "normal", stage: "wash", batch_id: "BATCH-101", health: 0.98, oee: 0.91, throughput_per_hour: 5 },
  { id: "washer-2", asset_tag: "WASH-02", type: "washer", status: "idle", mode: "normal", stage: "waiting_for_product", health: 0.97, oee: 0.88, throughput_per_hour: 4 },
  { id: "dryer-1", asset_tag: "DRY-01", type: "dryer", status: "running", mode: "normal", stage: "dry", batch_id: "BATCH-099", health: 0.96, oee: 0.89, throughput_per_hour: 5 },
];

const operationalSnapshot = {
  contract_version: "monitor.operations.v1",
  run_id: "laundry-run-1",
  simulation_minute: 13,
  scenario: "Laundry fleet",
  scope: { plant_id: "LAUNDRY-PLANT-01", asset_ids: assets.map((asset) => asset.id) },
  work_context: { active_batch_ids: ["BATCH-101", "BATCH-099"] },
  source_health: { source_id: "iiot-laundry-fleet", status: "connected", connected: true, quality: "good" },
  state: { operating_state: "running", operating_mode: "automatic", asset_condition: "healthy", data_health: "healthy", running_count: 2, waiting_for_product_count: 1 },
  intake: { queue_len: 4, in_progress: 2, completed: 9 },
  assets,
  observations: [],
};

const produceProduct = {
  contract_version: "monitor.produce.v1",
  work_context: operationalSnapshot.work_context,
  assets,
  intake: operationalSnapshot.intake,
  downtime_candidates: [{ event_id: "EV-STARVE-1", event_type: "product_starvation_detected", fact_label: "Inferred", scope: { asset_tag: "WASH-02" } }],
  cycle_events: [{ event_id: "EV-CYCLE-1", event_type: "production_cycle_completed", fact_label: "Observed", scope: { asset_tag: "DRY-01" } }],
  facts: [],
  data_quality: { status: "ready" },
};

const optimizeProduct = {
  contract_version: "monitor.optimize.v1",
  assets,
  operational_state_snapshot: { average_oee: 0.89, total_throughput_per_hour: 14, total_target_per_hour: 16, completed_batches: 9 },
  data_readiness: { status: "ready", identity_complete: true, source_quality: "good" },
  production_loss_events: [{ event_id: "EV-LOSS-1", event_type: "production_loss_event", fact_label: "Calculated", scope: { asset_tag: "WASH-02" } }],
  constraints: [{ event_id: "EV-CONSTRAINT-1", event_type: "constraint_state_changed", fact_label: "Observed", scope: { asset_tag: "WASH-02" } }],
  recommendation_invalidating_events: [],
  intervention_outcomes: [],
};

function response(output: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ success: true, output }) } as Response);
}

beforeEach(() => {
  simulatorOffline = false;
  window.localStorage.clear();
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("monitor_live_operations")) {
      return response(simulatorOffline ? { ...operationalSnapshot, source_health: { source_id: "iiot-laundry-fleet", status: "disconnected", connected: false, quality: "bad" }, state: { operating_state: "unknown", operating_mode: "unknown", asset_condition: "unknown", data_health: "disconnected" }, assets: [], intake: {} } : operationalSnapshot);
    }
    if (url.includes("monitor_source_health")) {
      return response({ overall_status: simulatorOffline ? "disconnected" : "healthy", data_health: simulatorOffline ? "disconnected" : "healthy", sources: [{ source_id: "iiot-laundry-fleet", domain: "laundry", status: simulatorOffline ? "disconnected" : "connected", connected: !simulatorOffline, quality: simulatorOffline ? "bad" : "good", calibration_status: "simulator_calibrated" }] });
    }
    if (url.includes("monitor_event_timeline")) return response({ contract_version: "monitor.operations.v1", latest_seq: 0, events: [], warnings: [] });
    if (url.includes("monitor_fleet")) return response({ machines: assets });
    if (url.includes("monitor_produce_data_product")) return response(produceProduct);
    if (url.includes("monitor_optimize_data_product")) return response(optimizeProduct);
    return response({});
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Monitor dashboard", () => {
  it("declares the five task-oriented views", () => {
    expect(TABS.map((tab) => tab.id)).toEqual(["live_operations", "event_timeline", "assets", "data_health", "data_products"]);
  });

  it("renders laundry operations and supports explicit view navigation", async () => {
    render(<Dashboard apiBase="http://monitor.test" theme="dark" />);
    expect(await screen.findByText("Live operational truth")).toBeTruthy();
    expect(await screen.findByText("Laundry fleet")).toBeTruthy();
    expect(screen.getByText("BATCH-101, BATCH-099")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Event Timeline" }));
    await waitFor(() => expect(screen.getByText("Event timeline")).toBeTruthy());
    expect(screen.getByText(/No operational facts yet/)).toBeTruthy();
  });

  it("owns and persists light mode and Vietnamese inside Monitor", async () => {
    const { container } = render(<Dashboard apiBase="http://monitor.test" theme="dark" />);
    await screen.findByText("Live operational truth");
    fireEvent.click(screen.getByRole("button", { name: "Use light appearance" }));
    expect(container.querySelector(".monitor-shell")?.getAttribute("data-theme")).toBe("light");
    expect(window.localStorage.getItem("monitor-theme")).toBe("light");

    fireEvent.click(screen.getByRole("button", { name: "Use Vietnamese" }));
    expect(await screen.findByText("Sự thật vận hành trực tiếp")).toBeTruthy();
    expect(container.querySelector(".monitor-shell")?.getAttribute("lang")).toBe("vi");
    expect(window.localStorage.getItem("monitor-lang")).toBe("vi");
  });

  it("keeps the live dashboard shape while the simulator is offline", async () => {
    simulatorOffline = true;
    const { container } = render(<Dashboard apiBase="http://monitor.test" theme="light" />);
    expect(await screen.findAllByText("Simulator is not connected")).not.toHaveLength(0);
    expect(container.querySelectorAll(".metric-card")).toHaveLength(4);
    expect((screen.getByLabelText("Question about the live laundry plant") as HTMLInputElement).disabled).toBe(true);
  });

  it("provides distinct Produce and Optimize consumer modes", async () => {
    render(<Dashboard apiBase="http://monitor.test" theme="dark" />);
    fireEvent.click(await screen.findByRole("button", { name: "Data Products" }));
    const modeGroup = await screen.findByRole("group", { name: "Data product view" });

    fireEvent.click(within(modeGroup).getByRole("button", { name: "Produce" }));
    expect(await screen.findByText("Laundry execution truth")).toBeTruthy();
    expect(screen.getByText("WASH-01")).toBeTruthy();

    fireEvent.click(within(modeGroup).getByRole("button", { name: "Optimize" }));
    expect(await screen.findByText("Optimization input truth")).toBeTruthy();
    expect(screen.getByText("89%")).toBeTruthy();
  });
});
