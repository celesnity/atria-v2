import { EmbinderProvider, useEmbinder, useRoute } from '@embinder/react';
import { useMascotMotionStore } from '../../stores/mascotMotion';
import { useEffect, useState, type ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { useModulesStore } from '../../stores/modules';
import {
  callModuleEmbinderAction,
  getModuleEmbinderContext,
  subscribeModuleEmbinderContext,
  type ModuleEmbinderContext,
} from '../ModuleDashboard/embinderModuleBridge';

type ReleaseArguments = { count?: number; product?: string };
type ServiceArguments = { machineId: string };
type ModuleArguments = { moduleName: string };
type ModuleTabArguments = { moduleName: string; tabId: string };
type TenantArguments = { slug: string };
type OptimizeSectionArguments = { section: 'today' | 'decision' | 'performance' | 'history' };
type OptimizeLanguageArguments = { language: 'en' | 'vi' };
type OptimizeThemeArguments = { theme: 'light' | 'dark' };
type OptimizeModeArguments = { mode: 'sim' | 'demo' };
type OptimizeRecommendationArguments = { index?: number };

const OPTIMIZE_MODULE = 'optimize_demo';

async function readJson(path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Atria operations request failed (${response.status}).`);
  return response.json();
}

async function openModule(moduleName: string, tabId?: string): Promise<{
  moduleName: string;
  tabId: string | null;
}> {
  const store = useModulesStore.getState();
  if (!store.modulesWithDashboards.some((module) => module.name === moduleName)) {
    await store.refresh();
  }

  const module = useModulesStore.getState().modulesWithDashboards.find((item) => item.name === moduleName);
  if (!module) throw new Error(`Module ${moduleName} is not available in this account.`);
  if (tabId && !module.tabs.some((tab) => tab.id === tabId)) {
    throw new Error(`Module ${moduleName} has no ${tabId} tab.`);
  }

  const latest = useModulesStore.getState();
  latest.openDashboard(moduleName);
  if (tabId) latest.setModuleTab(tabId);
  return { moduleName, tabId: tabId ?? module.tabs[0]?.id ?? null };
}

function OperationsCapabilities() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeModule = useModulesStore((state) => state.activeModuleDashboard);
  const activeTab = useModulesStore((state) => state.activeModuleTab);
  const modules = useModulesStore((state) => state.modulesWithDashboards);
  const [optimizeContext, setOptimizeContext] = useState<ModuleEmbinderContext | null>(() =>
    getModuleEmbinderContext(OPTIMIZE_MODULE),
  );

  useEffect(
    () => subscribeModuleEmbinderContext((moduleName, context) => {
      if (moduleName === OPTIMIZE_MODULE) setOptimizeContext(context);
    }),
    [],
  );

  useRoute(
    [
      { id: 'chat', label: 'Minder workspace', path: '/chat', destructive: false },
      { id: 'admin-tenants', label: 'Tenant administration', path: '/admin/tenants', destructive: false },
    ],
    { navigate: (path) => navigate(path) },
  );

  const callOptimize = async (action: string, args: Record<string, unknown> = {}) => {
    await openModule(OPTIMIZE_MODULE, 'guided');
    navigate('/chat');
    return callModuleEmbinderAction(OPTIMIZE_MODULE, action, args);
  };

  useEmbinder({
    name: 'current_screen',
    title: 'Inspect current screen',
    description: 'Read the current Atria route, open module, active tab, and the actions the visible screen exposes.',
    handler: () => ({
      route: location.pathname,
      open_module: activeModule,
      active_module_tab: activeTab,
      available_modules: modules.map((module) => ({
        name: module.name,
        title: module.display_name,
        tabs: module.tabs.map((tab) => ({ id: tab.id, label: tab.label })),
      })),
      optimize: optimizeContext,
    }),
    context: () => ({
      route: location.pathname,
      open_module: activeModule,
      active_module_tab: activeTab,
      optimize: optimizeContext,
    }),
  });

  useEmbinder({
    name: 'atria_read_operational_truth',
    title: 'Read live operations',
    description: 'Read Monitor’s current operational facts, source health, and evidence. This never changes the fleet.',
    handler: () => readJson('/api/operations/truth'),
  });

  useEmbinder({
    name: 'atria_open_module',
    title: 'Open a module',
    description: 'Open an available Atria module in the normal workspace. Use current_screen to discover module names and tabs.',
    input: { moduleName: z.string().min(1) },
    handler: async (raw) => {
      const args = raw as unknown as ModuleArguments;
      const result = await openModule(args.moduleName);
      navigate('/chat');
      return result;
    },
  });

  useEmbinder({
    name: 'atria_select_module_tab',
    title: 'Select a module tab',
    description: 'Open an available module and select one of its declared tabs.',
    input: { moduleName: z.string().min(1), tabId: z.string().min(1) },
    handler: async (raw) => {
      const args = raw as unknown as ModuleTabArguments;
      const result = await openModule(args.moduleName, args.tabId);
      navigate('/chat');
      return result;
    },
  });

  useEmbinder({
    name: 'atria_open_tenant_users',
    title: 'Open tenant users',
    description: 'Navigate to the user-management page for a tenant slug that the current user can administer.',
    input: { slug: z.string().min(1) },
    handler: (raw) => {
      const args = raw as unknown as TenantArguments;
      const path = `/admin/tenants/${encodeURIComponent(args.slug)}/users`;
      navigate(path);
      return { path, slug: args.slug };
    },
  });

  useEmbinder({
    name: 'optimize_navigate_section',
    title: 'Navigate Optimize',
    description: 'Open Optimize Guided and navigate to Today, Decisions, Performance, or History without changing an operational decision.',
    input: { section: z.enum(['today', 'decision', 'performance', 'history']) },
    handler: async (raw) => {
      const args = raw as unknown as OptimizeSectionArguments;
      return callOptimize('navigate_section', { section: args.section });
    },
  });

  useEmbinder({
    name: 'optimize_set_language',
    title: 'Set Optimize language',
    description: 'Set the visible Optimize Guided language to English or Vietnamese.',
    input: { language: z.enum(['en', 'vi']) },
    handler: async (raw) => {
      const args = raw as unknown as OptimizeLanguageArguments;
      return callOptimize('set_language', args);
    },
  });

  useEmbinder({
    name: 'optimize_set_theme',
    title: 'Set Optimize theme',
    description: 'Set the visible Optimize Guided theme to light or dark.',
    input: { theme: z.enum(['light', 'dark']) },
    handler: async (raw) => {
      const args = raw as unknown as OptimizeThemeArguments;
      return callOptimize('set_theme', args);
    },
  });

  useEmbinder({
    name: 'optimize_set_data_mode',
    title: 'Set Optimize data mode',
    description: 'Switch Optimize Guided between the live simulator and the clearly labelled demo scenario.',
    input: { mode: z.enum(['sim', 'demo']) },
    handler: async (raw) => {
      const args = raw as unknown as OptimizeModeArguments;
      return callOptimize('set_data_mode', args);
    },
  });

  useEmbinder({
    name: 'optimize_open_recommendation',
    title: 'Open an Optimize recommendation',
    description: 'Open a visible Optimize recommendation by its zero-based position in the current queue.',
    input: { index: z.number().int().min(0).optional() },
    handler: async (raw) => {
      const args = raw as unknown as OptimizeRecommendationArguments;
      return callOptimize('open_recommendation', args);
    },
  });

  useEmbinder({
    name: 'optimize_open_evidence',
    title: 'Open Optimize evidence',
    description: 'Open the evidence drawer for the current Optimize recommendation.',
    handler: () => callOptimize('open_evidence'),
  });

  useEmbinder({
    name: 'optimize_open_review',
    title: 'Open Optimize review',
    description: 'Open the review drawer for the current Optimize recommendation without executing it.',
    handler: () => callOptimize('open_review'),
  });

  useEmbinder({
    name: 'optimize_approve_recommendation',
    title: 'Approve and execute Optimize recommendation',
    description: 'Approve the current Optimize recommendation. This can dispatch a governed simulator action and always requires explicit human approval.',
    destructive: true,
    handler: () => callOptimize('approve_recommendation'),
  });

  useEmbinder({
    name: 'optimize_reject_recommendation',
    title: 'Reject Optimize recommendation',
    description: 'Record a rejection for the current Optimize recommendation. This is a critical decision and always requires explicit human approval.',
    destructive: true,
    handler: () => callOptimize('reject_recommendation'),
  });

  useEmbinder({
    name: 'atria_request_release_order',
    title: 'Request intake release',
    description: 'Prepare a product intake release through Optimize. The request is not executed until an operator approves it.',
    destructive: true,
    input: {
      count: z.number().int().min(1).max(20).optional(),
      product: z.string().min(1).optional(),
    },
    handler: (raw) => {
      const args = raw as unknown as ReleaseArguments;
      return readJson('/api/operations/orders', {
        count: args.count ?? 1,
        product: args.product,
        idempotency_key: crypto.randomUUID(),
      });
    },
  });

  useEmbinder({
    name: 'atria_request_service_order',
    title: 'Request machine service',
    description: 'Prepare service for one washer or dryer through Optimize. The request is not executed until an operator approves it.',
    destructive: true,
    input: { machineId: z.string().min(1) },
    handler: (raw) => {
      const args = raw as unknown as ServiceArguments;
      return readJson('/api/operations/service-orders', {
        machine_id: args.machineId,
        idempotency_key: crypto.randomUUID(),
      });
    },
  });

  return null;
}

export function EmbindOperationsBridge({ children }: { children: ReactNode }) {
  const relayUrl = import.meta.env.VITE_EMBINDER_RELAY_URL || 'ws://127.0.0.1:7331/app';
  const mascotMotion = useMascotMotionStore((state) => state.preference);
  return (
    <EmbinderProvider url={relayUrl} viz motion={mascotMotion}>
      <OperationsCapabilities />
      {children}
    </EmbinderProvider>
  );
}
