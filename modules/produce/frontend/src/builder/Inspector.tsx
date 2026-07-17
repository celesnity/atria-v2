import { useState } from 'react';
import {
  Drawer,
  TextInput,
  Textarea,
  NumberInput,
  Switch,
  Select,
  PasswordInput,
  Button,
  Stack,
  Divider,
  Text,
  Group,
} from '@mantine/core';
import { IconDeviceFloppy } from '@tabler/icons-react';
import { useMinderPopupTarget } from 'minder-ui-sdk';
import type { NodeTypeMeta, NodePortMeta } from './engineApi';
import { createTemplate } from './engineApi';
import { widgetFor } from './fields';
import type { FlowNodeType } from './nodes/FlowNode';
import { useToast } from '../ui/Toast';

// ---------------------------------------------------------------------------
// Portal helpers (mirrors the pattern from src/ui/selects.tsx)
// ---------------------------------------------------------------------------

function usePortalTarget(): HTMLElement | null {
  const sdkTarget = useMinderPopupTarget();
  const scoped =
    typeof document !== 'undefined'
      ? (document.querySelector('[data-produce-dashboard]') as HTMLElement | null)
      : null;
  return sdkTarget ?? scoped;
}

function useCombobox() {
  const target = usePortalTarget();
  return { withinPortal: true, portalProps: target ? { target } : undefined };
}

// ---------------------------------------------------------------------------
// Condition operators for decision nodes
// ---------------------------------------------------------------------------

const CONDITION_OPERATORS = [
  '==',
  '!=',
  '>',
  '<',
  '>=',
  '<=',
  'contains',
  'not_contains',
  'is_empty',
  'is_not_empty',
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface InspectorProps {
  engineBase: string;
  node: FlowNodeType | null;
  nodeTypeMeta: NodeTypeMeta | null;
  scopePath?: string;
  onChange: (patch: { key?: string; label?: string; config?: Record<string, unknown> }) => void;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// JSON field with inline validation
// ---------------------------------------------------------------------------

function JsonField({
  label,
  description,
  required,
  value,
  onCommit,
}: {
  label: string;
  description?: string;
  required?: boolean;
  value: unknown;
  onCommit: (parsed: unknown) => void;
}) {
  const [raw, setRaw] = useState(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value ?? '');
    }
  });
  const [error, setError] = useState<string | null>(null);

  function handleBlur() {
    try {
      const parsed = JSON.parse(raw);
      setError(null);
      onCommit(parsed);
    } catch {
      setError('Invalid JSON');
    }
  }

  return (
    <Textarea
      label={label}
      description={description}
      required={required}
      value={raw}
      onChange={(e) => {
        setRaw(e.currentTarget.value);
        setError(null);
      }}
      onBlur={handleBlur}
      error={error}
      autosize
      minRows={3}
      maxRows={8}
      styles={{ input: { fontFamily: 'Fira Code, monospace', fontSize: 12 } }}
    />
  );
}

// ---------------------------------------------------------------------------
// Per-port field renderer
// ---------------------------------------------------------------------------

function PortField({
  port,
  value,
  onChange,
  comboboxProps,
}: {
  port: NodePortMeta;
  value: unknown;
  onChange: (v: unknown) => void;
  comboboxProps: ReturnType<typeof useCombobox>;
}) {
  const widget = widgetFor(port);
  const label = port.display_name;
  const description = port.description || undefined;
  const required = port.required;

  switch (widget) {
    case 'text':
      return (
        <TextInput
          label={label}
          description={description}
          required={required}
          value={String(value ?? '')}
          onChange={(e) => onChange(e.currentTarget.value)}
        />
      );

    case 'textarea':
      return (
        <Textarea
          label={label}
          description={description}
          required={required}
          value={String(value ?? '')}
          onChange={(e) => onChange(e.currentTarget.value)}
          autosize
          minRows={2}
          maxRows={6}
        />
      );

    case 'number':
      return (
        <NumberInput
          label={label}
          description={description}
          required={required}
          value={typeof value === 'number' ? value : undefined}
          onChange={(v) => onChange(v)}
        />
      );

    case 'switch':
      return (
        <Switch
          label={label}
          description={description}
          required={required}
          checked={!!value}
          onChange={(e) => onChange(e.currentTarget.checked)}
        />
      );

    case 'select':
      return (
        <Select
          label={label}
          description={description}
          required={required}
          data={port.options}
          value={value != null ? String(value) : null}
          onChange={(v) => onChange(v)}
          comboboxProps={comboboxProps}
          allowDeselect={!required}
        />
      );

    case 'password':
      return (
        <PasswordInput
          label={label}
          description={description}
          required={required}
          value={String(value ?? '')}
          onChange={(e) => onChange(e.currentTarget.value)}
        />
      );

    case 'json':
      return (
        <JsonField
          label={label}
          description={description}
          required={required}
          value={value}
          onCommit={onChange}
        />
      );

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Decision condition section
// ---------------------------------------------------------------------------

type Condition = { left?: string; operator?: string; right?: string };

function DecisionCondition({
  condition,
  onChange,
  comboboxProps,
}: {
  condition: Condition;
  onChange: (c: Condition) => void;
  comboboxProps: ReturnType<typeof useCombobox>;
}) {
  return (
    <Stack gap="xs">
      <Text size="sm" fw={500}>
        Condition
      </Text>
      <TextInput
        label="Left"
        value={condition.left ?? ''}
        onChange={(e) => onChange({ ...condition, left: e.currentTarget.value })}
        placeholder="e.g. status"
      />
      <Select
        label="Operator"
        data={CONDITION_OPERATORS}
        value={condition.operator ?? null}
        onChange={(v) => onChange({ ...condition, operator: v ?? undefined })}
        comboboxProps={comboboxProps}
        allowDeselect={false}
        placeholder="Select operator"
      />
      <TextInput
        label="Right"
        value={condition.right ?? ''}
        onChange={(e) => onChange({ ...condition, right: e.currentTarget.value })}
        placeholder="e.g. approved"
      />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Inspector
// ---------------------------------------------------------------------------

export default function Inspector({
  engineBase,
  node,
  nodeTypeMeta,
  scopePath,
  onChange,
  onClose,
}: InspectorProps) {
  const { notify } = useToast();
  const comboboxProps = useCombobox();
  const target = usePortalTarget();

  const [saving, setSaving] = useState(false);

  async function handleSaveAsTemplate() {
    if (!node) return;
    setSaving(true);
    try {
      await createTemplate(engineBase, {
        key: node.data.key,
        name: node.data.label || node.data.key,
        base_kind: node.data.node_type,
        config: node.data.config,
        scope_path: scopePath,
      });
      notify('Saved as template', 'ok');
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Failed to save template', 'err');
    } finally {
      setSaving(false);
    }
  }

  const config = node?.data.config ?? {};
  const isDecision = node?.data.node_type === 'decision';
  const condition = (config.condition ?? {}) as Condition;

  return (
    <Drawer
      opened={!!node}
      onClose={onClose}
      position="right"
      title={
        <Text fw={600} size="sm">
          {node ? `${node.data.node_type} node` : 'Inspector'}
        </Text>
      }
      size="sm"
      zIndex={2_147_483_000}
      portalProps={target ? { target } : undefined}
    >
      {node && (
        <Stack gap="md" p="xs">
          {/* Key + Label */}
          <TextInput
            label="Key"
            description="Unique identifier for this node"
            required
            value={node.data.key}
            onChange={(e) => onChange({ key: e.currentTarget.value })}
            styles={{ input: { fontFamily: 'Fira Code, monospace' } }}
          />
          <TextInput
            label="Label"
            description="Human-readable name"
            value={node.data.label ?? ''}
            onChange={(e) => onChange({ label: e.currentTarget.value })}
          />

          {/* Port fields */}
          {nodeTypeMeta && nodeTypeMeta.inputs.length > 0 && (
            <>
              <Divider label="Configuration" labelPosition="left" />
              {nodeTypeMeta.inputs.map((port: NodePortMeta) => (
                <PortField
                  key={port.name}
                  port={port}
                  value={config[port.name]}
                  onChange={(v) =>
                    onChange({ config: { ...config, [port.name]: v } })
                  }
                  comboboxProps={comboboxProps}
                />
              ))}
            </>
          )}

          {/* Decision condition */}
          {isDecision && (
            <>
              <Divider label="Condition" labelPosition="left" />
              <DecisionCondition
                condition={condition}
                onChange={(c) =>
                  onChange({ config: { ...config, condition: c } })
                }
                comboboxProps={comboboxProps}
              />
            </>
          )}

          <Divider />

          {/* Save as template */}
          <Group justify="flex-end">
            <Button
              size="xs"
              variant="light"
              leftSection={<IconDeviceFloppy size={14} />}
              loading={saving}
              onClick={handleSaveAsTemplate}
            >
              Save as template
            </Button>
          </Group>
        </Stack>
      )}
    </Drawer>
  );
}
