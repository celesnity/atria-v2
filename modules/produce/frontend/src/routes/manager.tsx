import { Stack } from '@mantine/core';
import ManagerCharts from '../panels/ManagerCharts';
import ReportPanel from '../panels/ReportPanel';

export default function ManagerRoute({ apiBase }: { apiBase: string }) {
  return (
    <Stack gap="md">
      <ManagerCharts apiBase={apiBase} />
      <ReportPanel apiBase={apiBase} />
    </Stack>
  );
}
