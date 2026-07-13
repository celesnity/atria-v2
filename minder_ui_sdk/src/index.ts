export { defineDashboard } from './defineDashboard';
export type {
  TabMeta,
  DashboardProps,
  DashboardConfig,
  DashboardComponent,
} from './types';
export {
  MinderThemeProvider,
  useMinderTheme,
  tokensFor,
} from './theme';
export type { MinderTheme, MinderTokens } from './theme';
export { useModuleEvents, useAgentContext } from './agentContext';
export type {
  EventEnvelope,
  EventActor,
  AgentContext,
  UseModuleEventsOptions,
} from './agentContext';
export { DecisionPacket, useDecision } from './decision';
export type {
  DecisionPacketData,
  Decision,
  DecisionVerdict,
  Assumption,
} from './decision';
export {
  AgentDriverProvider,
  useAgentForm,
  useAgentHighlight,
  useAgentActivity,
} from './agentDriver';
export type {
  UiIntent,
  AgentDriverProviderProps,
  UseAgentFormArgs,
  AgentFormState,
  AgentActivity,
} from './agentDriver';
export {
  AgentPresence,
  GhostCursor,
  AgentBadge,
  useAgentPresence,
  attributionLabel,
} from './presence';
export type {
  AgentPresenceState,
  AgentPresenceInfo,
  AgentPresenceProps,
  UseAgentPresenceOptions,
} from './presence';
export { Agent, AgentRegistryProvider } from './agentSurface/AgentSurface';
export type { AgentRegistryProviderProps } from './agentSurface/AgentSurface';
export { createRegistry, MAX_VALUE_CHARS } from './agentSurface/registry';
export type { UiSnapshot, DataEntry, ActionEntry, Registry } from './agentSurface/registry';
