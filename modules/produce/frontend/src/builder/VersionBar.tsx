/**
 * VersionBar — validate/publish toolbar + versions menu for the workflow builder.
 */
import { useState, useCallback } from 'react';
import {
  Group,
  Button,
  Badge,
  Menu,
  Modal,
  Textarea,
  Alert,
  Text,
  Tooltip,
  Loader,
} from '@mantine/core';
import {
  IconShieldCheck,
  IconRocket,
  IconChevronDown,
  IconAlertCircle,
  IconHistory,
} from '@tabler/icons-react';
import { useMinderPopupTarget } from 'minder-ui-sdk';
import {
  validateWorkflow,
  publishWorkflow,
  listVersions,
  revertVersion,
} from './engineApi';
import { mapIssues } from './issues';
import type { WorkflowGraph, VersionSummary } from './engineApi';
import type { FlowNodeData } from './nodes/FlowNode';
import type { Node } from '@xyflow/react';
import { useToast } from '../ui/Toast';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface VersionBarProps {
  engineBase: string;
  workflowId: number;
  getGraph: () => WorkflowGraph;
  nodes: Node<FlowNodeData>[];
  setNodeInvalid: (invalidKeys: Set<string>) => void;
  onDraftReload: () => void;
}

// ---------------------------------------------------------------------------
// VersionBar
// ---------------------------------------------------------------------------

export default function VersionBar({
  engineBase,
  workflowId,
  getGraph,
  nodes,
  setNodeInvalid,
  onDraftReload,
}: VersionBarProps) {
  const { notify } = useToast();
  const popupTarget = useMinderPopupTarget();
  const portalProps = popupTarget ? { target: popupTarget } : undefined;

  // ------------------------------------------------------------------
  // Validation state
  // ------------------------------------------------------------------
  const [validating, setValidating] = useState(false);
  const [generalIssues, setGeneralIssues] = useState<string[]>([]);
  const [issueCount, setIssueCount] = useState(0);
  const [validated, setValidated] = useState(false); // true after a clean validation

  const handleValidate = useCallback(async () => {
    setValidating(true);
    setValidated(false);
    try {
      const graph = getGraph();
      const result = await validateWorkflow(engineBase, workflowId);
      const mapped = mapIssues(result.issues, graph);

      // Mark invalid nodes
      const invalidKeys = new Set(Object.keys(mapped.byNodeKey));
      setNodeInvalid(invalidKeys);

      setGeneralIssues(mapped.general);
      const total = result.issues.length;
      setIssueCount(total);

      if (total === 0) {
        setValidated(true);
        notify('Validation passed', 'ok');
      }
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Validation failed', 'err');
    } finally {
      setValidating(false);
    }
  }, [engineBase, workflowId, getGraph, setNodeInvalid, notify]);

  // ------------------------------------------------------------------
  // Publish state
  // ------------------------------------------------------------------
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishNote, setPublishNote] = useState('');
  const [publishing, setPublishing] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);

  const handlePublish = useCallback(async () => {
    setPublishing(true);
    try {
      const result = await publishWorkflow(engineBase, workflowId, publishNote);
      setCurrentVersion(result.version);
      notify(`Published v${result.version}`, 'ok');
      setPublishOpen(false);
      setPublishNote('');
      // Clear issue state after successful publish
      setIssueCount(0);
      setGeneralIssues([]);
      setNodeInvalid(new Set());
      setValidated(false);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Publish failed', 'err');
    } finally {
      setPublishing(false);
    }
  }, [engineBase, workflowId, publishNote, setNodeInvalid, notify]);

  // ------------------------------------------------------------------
  // Versions menu
  // ------------------------------------------------------------------
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [reverting, setReverting] = useState(false);

  const loadVersions = useCallback(async () => {
    setVersionsLoading(true);
    try {
      const v = await listVersions(engineBase, workflowId);
      setVersions(v);
    } catch (err) {
      notify(err instanceof Error ? err.message : 'Failed to load versions', 'err');
    } finally {
      setVersionsLoading(false);
    }
  }, [engineBase, workflowId, notify]);

  const handleRevert = useCallback(
    async (version: number) => {
      setReverting(true);
      try {
        await revertVersion(engineBase, workflowId, version);
        notify(`Reverted to v${version}`, 'ok');
        onDraftReload();
        // Clear issue overlays after revert
        setNodeInvalid(new Set());
        setIssueCount(0);
        setGeneralIssues([]);
        setValidated(false);
      } catch (err) {
        notify(err instanceof Error ? err.message : 'Revert failed', 'err');
      } finally {
        setReverting(false);
      }
    },
    [engineBase, workflowId, onDraftReload, setNodeInvalid, notify],
  );

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  const hasIssues = issueCount > 0;

  return (
    <>
      <Group gap="xs">
        {/* General issues alert */}
        {generalIssues.length > 0 && (
          <Alert
            icon={<IconAlertCircle size={14} />}
            color="red"
            p="xs"
            style={{ maxWidth: 340 }}
          >
            {generalIssues.map((msg: string, i: number) => (
              <Text key={i} size="xs">{msg}</Text>
            ))}
          </Alert>
        )}

        {/* Issue count badge */}
        {hasIssues && (
          <Badge color="red" size="sm" variant="filled">
            {issueCount} issue{issueCount !== 1 ? 's' : ''}
          </Badge>
        )}

        {/* Current version chip */}
        {currentVersion !== null && (
          <Badge color="blue" size="sm" variant="light">
            v{currentVersion}
          </Badge>
        )}

        {/* Validate */}
        <Button
          size="xs"
          variant="light"
          color="blue"
          leftSection={validating ? <Loader size={12} /> : <IconShieldCheck size={14} />}
          onClick={handleValidate}
          disabled={validating}
          aria-label="Validate workflow"
        >
          Validate
        </Button>

        {/* Publish */}
        <Tooltip
          label={hasIssues ? 'Fix validation issues before publishing' : 'Publish workflow'}
          disabled={!hasIssues}
          portalProps={portalProps}
          withinPortal
        >
          <Button
            size="xs"
            variant="filled"
            color="green"
            leftSection={<IconRocket size={14} />}
            onClick={() => setPublishOpen(true)}
            disabled={hasIssues}
            aria-label="Publish workflow"
          >
            Publish
          </Button>
        </Tooltip>

        {/* Versions menu */}
        <Menu
          onOpen={loadVersions}
          withinPortal
          portalProps={portalProps}
        >
          <Menu.Target>
            <Button
              size="xs"
              variant="subtle"
              rightSection={<IconChevronDown size={12} />}
              leftSection={<IconHistory size={14} />}
              aria-label="Version history"
            >
              Versions
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            {versionsLoading && (
              <Menu.Item disabled>
                <Loader size={12} /> Loading…
              </Menu.Item>
            )}
            {!versionsLoading && versions.length === 0 && (
              <Menu.Item disabled>No published versions</Menu.Item>
            )}
            {versions.map((v: VersionSummary) => (
              <Menu.Item
                key={v.id}
                disabled={reverting}
                onClick={() => handleRevert(v.version)}
              >
                <Group gap="xs">
                  <Badge size="xs" variant="light">v{v.version}</Badge>
                  <Text size="xs" c="dimmed">{v.note ?? v.status}</Text>
                </Group>
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      </Group>

      {/* Publish modal */}
      <Modal
        opened={publishOpen}
        onClose={() => setPublishOpen(false)}
        title="Publish Workflow"
        size="sm"
        withinPortal
        portalProps={portalProps}
        zIndex={2_147_483_001}
      >
        <Textarea
          label="Release note (optional)"
          placeholder="Describe what changed in this version…"
          value={publishNote}
          onChange={(e) => setPublishNote(e.currentTarget.value)}
          minRows={3}
          mb="md"
        />
        <Group justify="flex-end" gap="sm">
          <Button size="sm" variant="subtle" onClick={() => setPublishOpen(false)} disabled={publishing}>
            Cancel
          </Button>
          <Button
            size="sm"
            color="green"
            leftSection={<IconRocket size={14} />}
            loading={publishing}
            onClick={handlePublish}
          >
            Publish
          </Button>
        </Group>
      </Modal>
    </>
  );
}
