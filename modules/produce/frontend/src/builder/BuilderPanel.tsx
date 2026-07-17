/**
 * BuilderPanel — composes WorkflowList and WorkflowBuilder.
 * null selection → list; set → builder with onBack.
 */
import { useState } from 'react';
import WorkflowList from './WorkflowList';
import WorkflowBuilder from './WorkflowBuilder';
import type { WorkflowSummary } from './engineApi';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface BuilderPanelProps {
  apiBase: string;
  engineBase?: string;
  scopePath?: string;
}

// ---------------------------------------------------------------------------
// BuilderPanel
// ---------------------------------------------------------------------------

export default function BuilderPanel({
  apiBase,
  engineBase,
  scopePath = 'site',
}: BuilderPanelProps) {
  const base = engineBase ?? apiBase;
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowSummary | null>(null);

  if (selectedWorkflow) {
    return (
      <WorkflowBuilder
        engineBase={base}
        workflow={selectedWorkflow}
        onBack={() => setSelectedWorkflow(null)}
        scopePath={scopePath}
      />
    );
  }

  return (
    <WorkflowList
      engineBase={base}
      scopePath={scopePath}
      onOpen={(workflow) => setSelectedWorkflow(workflow)}
    />
  );
}
