/**
 * WorkflowList — list, create, duplicate, and rename workflows.
 */
import { useState, type ReactNode } from 'react';
import {
  Group,
  Text,
  TextInput,
  Button,
  Stack,
  Badge,
  ActionIcon,
  Loader,
  Alert,
  Menu,
} from '@mantine/core';
import {
  IconPlus,
  IconAlertCircle,
  IconDotsVertical,
  IconEdit,
  IconCopy,
  IconFolderOpen,
} from '@tabler/icons-react';
import { useMinderPopupTarget } from 'minder-ui-sdk';
import DataTable, { type Column } from '../ui/DataTable';
import { useApiQuery } from '../hooks/useApiQuery';
import {
  createWorkflow,
  renameWorkflow,
  duplicateWorkflow,
} from './engineApi';
import type { WorkflowSummary } from './engineApi';
import { useToast } from '../ui/Toast';
import { useQueryClient } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface WorkflowListProps {
  engineBase: string;
  scopePath: string;
  onOpen: (workflow: WorkflowSummary) => void;
}

// ---------------------------------------------------------------------------
// Rename inline form
// ---------------------------------------------------------------------------

function RenameForm({
  current,
  onRename,
  onCancel,
}: {
  current: string;
  onRename: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(current);
  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput
        size="xs"
        value={value}
        onChange={(e) => setValue(e.currentTarget.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onRename(value);
          if (e.key === 'Escape') onCancel();
        }}
        autoFocus
        style={{ flex: 1 }}
      />
      <Button size="xs" onClick={() => onRename(value)} disabled={!value.trim()}>
        Save
      </Button>
      <Button size="xs" variant="subtle" onClick={onCancel}>
        Cancel
      </Button>
    </Group>
  );
}

// ---------------------------------------------------------------------------
// WorkflowList
// ---------------------------------------------------------------------------

export default function WorkflowList({ engineBase, scopePath, onOpen }: WorkflowListProps) {
  const { notify } = useToast();
  const popupTarget = useMinderPopupTarget();
  const portalProps = popupTarget ? { target: popupTarget } : undefined;
  const queryClient = useQueryClient();

  const listPath = `/workflows?scope_path=${encodeURIComponent(scopePath)}`;
  const { data: workflows, isLoading, error, refetch } = useApiQuery<WorkflowSummary[]>(
    engineBase,
    listPath,
  );

  // Invalidate cached list
  const invalidateList = () => {
    queryClient.invalidateQueries({ queryKey: ['produce', engineBase, listPath] });
    refetch();
  };

  // ------------------------------------------------------------------
  // Create form
  // ------------------------------------------------------------------
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [createLoading, setCreateLoading] = useState(false);

  async function handleCreate() {
    const trimmedName = newName.trim();
    const trimmedKey = newKey.trim() || trimmedName.toLowerCase().replace(/\s+/g, '_');
    if (!trimmedName) return;
    setCreateLoading(true);
    try {
      await createWorkflow(engineBase, {
        key: trimmedKey,
        name: trimmedName,
        scope_path: scopePath,
      });
      notify(`Created "${trimmedName}"`, 'ok');
      setNewName('');
      setNewKey('');
      setCreating(false);
      invalidateList();
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Create failed', 'err');
    } finally {
      setCreateLoading(false);
    }
  }

  // ------------------------------------------------------------------
  // Rename
  // ------------------------------------------------------------------
  const [renamingId, setRenamingId] = useState<number | null>(null);

  async function handleRename(id: number, name: string) {
    if (!name.trim()) return;
    try {
      await renameWorkflow(engineBase, id, name.trim());
      notify('Renamed', 'ok');
      setRenamingId(null);
      invalidateList();
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Rename failed', 'err');
    }
  }

  // ------------------------------------------------------------------
  // Duplicate
  // ------------------------------------------------------------------
  async function handleDuplicate(id: number) {
    try {
      await duplicateWorkflow(engineBase, id);
      notify('Duplicated', 'ok');
      invalidateList();
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Duplicate failed', 'err');
    }
  }

  // ------------------------------------------------------------------
  // Table columns
  // ------------------------------------------------------------------
  const columns: Column<WorkflowSummary>[] = [
    {
      key: 'name',
      label: 'Name',
      render: (row) =>
        renamingId === row.id ? (
          <RenameForm
            current={row.name}
            onRename={(name) => handleRename(row.id, name)}
            onCancel={() => setRenamingId(null)}
          />
        ) : (
          <Text
            size="sm"
            fw={500}
            style={{ cursor: 'pointer' }}
            onClick={() => onOpen(row)}
          >
            {row.name}
          </Text>
        ),
    },
    {
      key: 'current_version_id',
      label: 'Published version',
      render: (row) =>
        row.current_version_id ? (
          <Badge size="xs" variant="light" color="blue">
            v{row.current_version_id}
          </Badge>
        ) : (
          <Text size="xs" c="dimmed">Draft</Text>
        ),
    },
    {
      key: 'scope_path',
      label: 'Scope',
      render: (row) => (
        <Text size="xs" c="dimmed" style={{ fontFamily: 'Fira Code, monospace' }}>
          {row.scope_path}
        </Text>
      ),
    },
    {
      key: 'actions',
      label: '',
      render: (row): ReactNode => (
        <Group gap={4} justify="flex-end" wrap="nowrap">
          <ActionIcon
            size="sm"
            variant="subtle"
            aria-label={`Open ${row.name}`}
            onClick={() => onOpen(row)}
          >
            <IconFolderOpen size={14} />
          </ActionIcon>
          <Menu withinPortal portalProps={portalProps}>
            <Menu.Target>
              <ActionIcon size="sm" variant="subtle" aria-label="Row actions">
                <IconDotsVertical size={14} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item
                leftSection={<IconEdit size={14} />}
                onClick={() => setRenamingId(row.id)}
              >
                Rename
              </Menu.Item>
              <Menu.Item
                leftSection={<IconCopy size={14} />}
                onClick={() => handleDuplicate(row.id)}
              >
                Duplicate
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      ),
    },
  ];

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <Stack gap="md">
      {/* Header row */}
      <Group justify="space-between" align="center">
        <Text fw={600} size="sm">Workflows</Text>
        <Button
          size="xs"
          leftSection={<IconPlus size={14} />}
          onClick={() => setCreating(true)}
        >
          New workflow
        </Button>
      </Group>

      {/* Create form */}
      {creating && (
        <Stack gap="xs" p="sm" style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 8 }}>
          <Text size="xs" fw={600} c="dimmed">New workflow</Text>
          <TextInput
            size="sm"
            placeholder="Name"
            value={newName}
            onChange={(e) => setNewName(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); }}
            autoFocus
          />
          <TextInput
            size="sm"
            placeholder="Key (auto-generated if empty)"
            value={newKey}
            onChange={(e) => setNewKey(e.currentTarget.value)}
            styles={{ input: { fontFamily: 'Fira Code, monospace' } }}
          />
          <Group gap="xs" justify="flex-end">
            <Button size="xs" variant="subtle" onClick={() => { setCreating(false); setNewName(''); setNewKey(''); }}>
              Cancel
            </Button>
            <Button size="xs" onClick={handleCreate} loading={createLoading} disabled={!newName.trim()}>
              Create
            </Button>
          </Group>
        </Stack>
      )}

      {/* Loading / error / table */}
      {isLoading && (
        <Group justify="center" py="xl">
          <Loader size="sm" />
        </Group>
      )}
      {error && (
        <Alert icon={<IconAlertCircle size={14} />} color="red" p="xs">
          <Text size="xs">{String(error)}</Text>
        </Alert>
      )}
      {!isLoading && !error && (
        <DataTable
          columns={columns as unknown as Column<Record<string, unknown>>[]}
          rows={(workflows ?? []) as unknown as Record<string, unknown>[]}
          empty="No workflows yet — create one above"
        />
      )}
    </Stack>
  );
}
