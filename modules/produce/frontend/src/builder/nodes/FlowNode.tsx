import React, { memo } from 'react';
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { Paper, Text, Box, Group } from '@mantine/core';
import {
  IconPlayerPlay,
  IconFlag,
  IconUser,
  IconGitFork,
} from '@tabler/icons-react';
import type { NodeType } from '../engineApi';
import { ACCENT } from '../nodeColors';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FlowNodeData = {
  node_type: NodeType;
  key: string;
  label?: string;
  config: Record<string, unknown>;
  invalid?: boolean;
} & Record<string, unknown>;

export type FlowNodeType = Node<FlowNodeData>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type IconFC = React.FC<{ size?: number; color?: string }>;

const ICON_MAP: Record<NodeType, IconFC> = {
  begin: IconPlayerPlay as IconFC,
  end: IconFlag as IconFC,
  human: IconUser as IconFC,
  decision: IconGitFork as IconFC,
};

const handleBaseStyle: React.CSSProperties = {
  width: 10,
  height: 10,
  border: '2px solid',
  background: '#fff',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function FlowNode({ data }: NodeProps<FlowNodeType>) {
  const { node_type, key, label, invalid } = data as FlowNodeData;
  const accent = ACCENT[node_type] ?? '#94A3B8';
  const Icon = ICON_MAP[node_type] ?? IconUser;
  const isDecision = node_type === 'decision';

  return (
    <>
      {/* Target (left) handle */}
      <Handle
        type="target"
        position={Position.Left}
        style={{ ...handleBaseStyle, borderColor: accent }}
        aria-label="Input connection"
      />

      <Paper
        shadow="xs"
        style={{
          position: 'relative',
          minWidth: 160,
          padding: '8px 10px 8px 18px',
          cursor: 'pointer',
          overflow: 'visible',
        }}
        styles={{
          root: {
            '@media (prefers-reduced-motion: no-preference)': {
              transition: 'opacity 150ms ease, color 150ms ease',
            },
            '&:hover': {
              opacity: 0.85,
            },
          },
        }}
      >
        {/* Left accent bar */}
        <Box
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: 4,
            borderRadius: '4px 0 0 4px',
            background: accent,
          }}
        />

        <Group gap={6} wrap="nowrap" align="center">
          {/* Icon */}
          <Icon size={14} color={accent} aria-label={`${node_type} node`} />

          {/* Status dot */}
          <Box
            component="span"
            style={{
              display: 'inline-block',
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: invalid ? '#EF4444' : '#22C55E',
              flexShrink: 0,
              marginLeft: 'auto',
            }}
            aria-label={invalid ? 'Invalid node' : 'Valid node'}
          />
        </Group>

        {/* Key (monospace) */}
        <Text
          size="xs"
          mt={4}
          style={{ fontFamily: 'Fira Code, monospace', lineHeight: 1.3 }}
        >
          {key}
        </Text>

        {/* Label (muted) */}
        {label && (
          <Text size="xs" c="dimmed" mt={2} style={{ lineHeight: 1.2 }}>
            {label}
          </Text>
        )}
      </Paper>

      {/* Source (right) handle(s) */}
      {isDecision ? (
        <>
          {/* "pass" branch — top */}
          <Box
            style={{
              position: 'absolute',
              right: -48,
              top: '30%',
              transform: 'translateY(-50%)',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap', fontSize: 10 }}>
              pass
            </Text>
            <Handle
              type="source"
              position={Position.Right}
              id="pass"
              style={{
                ...handleBaseStyle,
                borderColor: accent,
                position: 'static',
                transform: 'none',
              }}
              aria-label="Pass branch output"
            />
          </Box>

          {/* "else" branch — bottom */}
          <Box
            style={{
              position: 'absolute',
              right: -48,
              top: '70%',
              transform: 'translateY(-50%)',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <Text size="xs" c="dimmed" style={{ whiteSpace: 'nowrap', fontSize: 10 }}>
              else
            </Text>
            <Handle
              type="source"
              position={Position.Right}
              id="else"
              style={{
                ...handleBaseStyle,
                borderColor: accent,
                position: 'static',
                transform: 'none',
              }}
              aria-label="Else branch output"
            />
          </Box>
        </>
      ) : (
        <Handle
          type="source"
          position={Position.Right}
          id="default"
          style={{ ...handleBaseStyle, borderColor: accent }}
          aria-label="Output connection"
        />
      )}
    </>
  );
}

export default memo(FlowNode);
