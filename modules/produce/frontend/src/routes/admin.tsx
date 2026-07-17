import { Grid, Stack } from '@mantine/core';
import ConfigPanel from '../panels/ConfigPanel';
import SopPanel from '../panels/SopPanel';
import SetupPanel from '../panels/SetupPanel';
import OeePanel from '../panels/OeePanel';

export default function AdminRoute({ apiBase }: { apiBase: string }) {
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <ConfigPanel apiBase={apiBase} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Stack gap="md">
          <SopPanel apiBase={apiBase} />
          <SetupPanel apiBase={apiBase} />
          <OeePanel apiBase={apiBase} />
        </Stack>
      </Grid.Col>
    </Grid>
  );
}
