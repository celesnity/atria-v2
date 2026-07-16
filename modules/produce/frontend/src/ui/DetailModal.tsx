import type { ReactNode } from 'react';
import { Modal, Box, LoadingOverlay, Group, ThemeIcon, Text } from '@mantine/core';
import { useMinderPopupTarget } from 'minder-ui-sdk';

/**
 * Reusable premium detail modal. Rendered via a portal targeted at the scoped
 * dashboard root ([data-produce-dashboard]) so Mantine CSS variables and the
 * active color scheme resolve correctly (the default body portal would fall
 * outside the module's cssVariablesSelector scope).
 */
export default function DetailModal({
  opened,
  onClose,
  title,
  subtitle,
  icon,
  loading = false,
  size = 'lg',
  children,
}: {
  opened: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  loading?: boolean;
  size?: string | number;
  children: ReactNode;
}) {
  // Portal into the SDK's host-level popup layer (a body-level node that escapes
  // the host's clipped/transformed module container and carries the module's
  // scoped Mantine CSS variables). Fall back to the in-page scoped root if the
  // layer isn't mounted yet — never the plain body, which lacks the scoped vars
  // and would render the modal transparent.
  const scoped =
    typeof document !== 'undefined'
      ? (document.querySelector('[data-produce-dashboard]') as HTMLElement | null)
      : null;
  const target = useMinderPopupTarget() ?? scoped ?? undefined;

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size={size}
      centered
      radius="lg"
      zIndex={2_147_483_000}
      portalProps={target ? { target } : undefined}
      overlayProps={{ backgroundOpacity: 0.55, blur: 4 }}
      transitionProps={{ transition: 'pop', duration: 200 }}
      title={
        <Group gap={12} align="center" wrap="nowrap">
          {icon ? (
            <ThemeIcon variant="gradient" gradient={{ from: 'cobalt.5', to: 'cobalt.7', deg: 135 }} size={38} radius="md">
              {icon}
            </ThemeIcon>
          ) : null}
          <div style={{ minWidth: 0 }}>
            <Text fw={700} fz={17} lh={1.2} style={{ letterSpacing: '-0.01em' }}>{title}</Text>
            {subtitle ? <Text size="xs" c="dimmed">{subtitle}</Text> : null}
          </div>
        </Group>
      }
      styles={{ title: { width: '100%' }, header: { paddingBottom: 8 }, body: { paddingTop: 12 } }}
    >
      <Box pos="relative" mih={80}>
        <LoadingOverlay visible={loading} overlayProps={{ blur: 1 }} loaderProps={{ color: 'cobalt', size: 'sm' }} />
        {children}
      </Box>
    </Modal>
  );
}
