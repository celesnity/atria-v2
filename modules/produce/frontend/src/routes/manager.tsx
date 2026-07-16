import { useState } from 'react';
import { Stack } from '@mantine/core';
import { IconChartBar, IconFileAnalytics } from '@tabler/icons-react';
import SubNav, { type SubTab } from '../ui/SubNav';
import ManagerCharts from '../panels/ManagerCharts';
import ReportPanel from '../panels/ReportPanel';

export default function ManagerRoute({ apiBase }: { apiBase: string }) {
  const [view, setView] = useState('charts');
  const tabs: SubTab[] = [
    { id: 'charts', label: 'Biểu đồ vận hành', icon: <IconChartBar size={16} /> },
    { id: 'reports', label: 'Báo cáo', icon: <IconFileAnalytics size={16} /> },
  ];

  return (
    <Stack gap="lg">
      <SubNav tabs={tabs} value={view} onChange={setView} />
      {view === 'charts' && <ManagerCharts apiBase={apiBase} />}
      {view === 'reports' && <ReportPanel apiBase={apiBase} />}
    </Stack>
  );
}
