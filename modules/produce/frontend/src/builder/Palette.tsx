import React from 'react';
import {
  Box,
  Text,
  Group,
  Stack,
  Loader,
  Alert,
  Divider,
  UnstyledButton,
} from '@mantine/core';
import {
  IconPlayerPlay,
  IconFlag,
  IconUser,
  IconGitFork,
  IconAlertCircle,
  IconTemplate,
} from '@tabler/icons-react';
import { useMinderPopupTarget } from 'minder-ui-sdk';
import type { NodeType, NodeTypeMeta, TemplateMeta } from './engineApi';
import { ACCENT } from './nodeColors';
import { useApiQuery } from '../hooks/useApiQuery';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PaletteProps {
  engineBase: string;
  scopePath: string;
  onAdd: (spec: { node_type: NodeType; templateConfig?: Record<string, unknown> }) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ICON_MAP: Record<NodeType, React.FC<{ size?: number; color?: string }>> = {
  begin: IconPlayerPlay,
  end: IconFlag,
  human: IconUser,
  decision: IconGitFork,
};

function NodeIcon({
  nodeType,
  size = 14,
}: {
  nodeType: string;
  size?: number;
}) {
  const type = nodeType as NodeType;
  const color = ACCENT[type] ?? '#94A3B8';
  const Icon = ICON_MAP[type] ?? IconTemplate;
  return <Icon size={size} color={color} />;
}

function AccentDot({ nodeType }: { nodeType: string }) {
  const color = ACCENT[nodeType as NodeType] ?? '#94A3B8';
  return (
    <Box
      component="span"
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

interface PaletteRowProps {
  nodeType: string;
  displayName: string;
  description?: string;
  onClick: () => void;
}

function PaletteRow({ nodeType, displayName, description, onClick }: PaletteRowProps) {
  return (
    <UnstyledButton
      onClick={onClick}
      onKeyDown={(e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      style={{
        display: 'block',
        width: '100%',
        padding: '6px 8px',
        borderRadius: 4,
        cursor: 'pointer',
        transition: 'background 150ms ease',
        textAlign: 'left',
      }}
      styles={{
        root: {
          '&:hover': {
            background: 'var(--mantine-color-default-hover)',
          },
          '&:focus-visible': {
            outline: '2px solid var(--mantine-color-blue-5)',
            outlineOffset: 1,
          },
        },
      }}
      tabIndex={0}
    >
      <Group gap={8} wrap="nowrap" align="flex-start">
        <Box pt={2}>
          <AccentDot nodeType={nodeType} />
        </Box>
        <NodeIcon nodeType={nodeType} />
        <Stack gap={1} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={600} style={{ lineHeight: 1.3 }}>
            {displayName}
          </Text>
          {description && (
            <Text size="xs" c="dimmed" style={{ lineHeight: 1.3 }}>
              {description}
            </Text>
          )}
        </Stack>
      </Group>
    </UnstyledButton>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function Palette({ engineBase, scopePath, onAdd }: PaletteProps) {
  // Portal target — kept for future Select/dropdown usage in Palette per convention.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _popupTarget = useMinderPopupTarget();

  const q = useApiQuery<{ primitives: NodeTypeMeta[]; templates: TemplateMeta[] }>(
    engineBase,
    '/node-types?scope_path=' + encodeURIComponent(scopePath),
  );

  if (q.isLoading) {
    return (
      <Box p="md" style={{ display: 'flex', justifyContent: 'center' }}>
        <Loader size="sm" />
      </Box>
    );
  }

  if (q.error) {
    return (
      <Alert icon={<IconAlertCircle size={14} />} color="red" p="xs">
        <Text size="xs">Failed to load node types</Text>
      </Alert>
    );
  }

  const primitives = q.data?.primitives ?? [];
  const templates = q.data?.templates ?? [];

  return (
    <Box>
      {/* Primitives section */}
      <Text size="xs" fw={700} c="dimmed" px={8} pt={8} pb={4} style={{ letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        Primitives
      </Text>
      <Stack gap={2} px={4}>
        {primitives.map((item) => (
          <PaletteRow
            key={item.node_type}
            nodeType={item.node_type}
            displayName={item.display_name}
            description={item.description}
            onClick={() => onAdd({ node_type: item.node_type as NodeType })}
          />
        ))}
        {primitives.length === 0 && (
          <Text size="xs" c="dimmed" px={4} py={4}>
            No primitives available
          </Text>
        )}
      </Stack>

      {templates.length > 0 && (
        <>
          <Divider my={8} />

          {/* Templates section */}
          <Text size="xs" fw={700} c="dimmed" px={8} pb={4} style={{ letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Templates
          </Text>
          <Stack gap={2} px={4}>
            {templates.map((item) => (
              <PaletteRow
                key={item.id}
                nodeType={item.base_kind}
                displayName={item.name}
                description={item.key}
                onClick={() =>
                  onAdd({
                    node_type: item.base_kind as NodeType,
                    templateConfig: item.config,
                  })
                }
              />
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}

export default Palette;
