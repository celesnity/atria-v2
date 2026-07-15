import ReportPanel from '../panels/ReportPanel';

export default function ManagerRoute({ apiBase }: { apiBase: string }) {
  return <ReportPanel apiBase={apiBase} />;
}
