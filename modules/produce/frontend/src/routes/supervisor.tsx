import { Grid, Stack } from '@mantine/core';
import OeeHero from '../panels/OeeHero';
import WorkPanel from '../panels/WorkPanel';
import HandoverPanel from '../panels/HandoverPanel';
import ScrapPanel from '../panels/ScrapPanel';
import ExceptionPanel from '../panels/ExceptionPanel';
import OeePanel from '../panels/OeePanel';

export default function SupervisorRoute({ apiBase }: { apiBase: string }) {
  return (
    <Stack gap="md">
      <OeeHero apiBase={apiBase} />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 6 }}><WorkPanel apiBase={apiBase} mode="load" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><HandoverPanel apiBase={apiBase} /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><ScrapPanel apiBase={apiBase} mode="hold" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><ExceptionPanel apiBase={apiBase} mode="escalated" /></Grid.Col>
      </Grid>
      <OeePanel apiBase={apiBase} />
    </Stack>
  );
}
