import { useState } from 'react';
import { Grid, Stack } from '@mantine/core';
import { IconGauge, IconRouteAltLeft, IconAlertHexagon } from '@tabler/icons-react';
import SubNav, { type SubTab } from '../ui/SubNav';
import OeeHero from '../panels/OeeHero';
import WorkPanel from '../panels/WorkPanel';
import HandoverPanel from '../panels/HandoverPanel';
import ScrapPanel from '../panels/ScrapPanel';
import ExceptionPanel from '../panels/ExceptionPanel';
import OeePanel from '../panels/OeePanel';

export default function SupervisorRoute({ apiBase }: { apiBase: string }) {
  const [view, setView] = useState('oee');
  const tabs: SubTab[] = [
    { id: 'oee', label: 'Hiệu suất (OEE)', icon: <IconGauge size={16} /> },
    { id: 'dispatch', label: 'Điều phối ca', icon: <IconRouteAltLeft size={16} /> },
    { id: 'exceptions', label: 'Ngoại lệ & Chất lượng', icon: <IconAlertHexagon size={16} /> },
  ];

  return (
    <Stack gap="lg">
      <SubNav tabs={tabs} value={view} onChange={setView} />

      {view === 'oee' && (
        <Stack gap="md">
          <OeeHero apiBase={apiBase} />
          <OeePanel apiBase={apiBase} />
        </Stack>
      )}

      {view === 'dispatch' && (
        <Grid gutter="md" align="flex-start">
          <Grid.Col span={{ base: 12, lg: 6 }}><WorkPanel apiBase={apiBase} mode="load" /></Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}><HandoverPanel apiBase={apiBase} /></Grid.Col>
        </Grid>
      )}

      {view === 'exceptions' && (
        <Grid gutter="md" align="flex-start">
          <Grid.Col span={{ base: 12, lg: 6 }}><ScrapPanel apiBase={apiBase} mode="hold" /></Grid.Col>
          <Grid.Col span={{ base: 12, lg: 6 }}><ExceptionPanel apiBase={apiBase} mode="escalated" /></Grid.Col>
        </Grid>
      )}
    </Stack>
  );
}
