import WorkPanel from '../panels/WorkPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ExceptionPanel from '../panels/ExceptionPanel';

export default function LeaderRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <WorkPanel apiBase={apiBase} mode="board" />
      <DowntimePanel apiBase={apiBase} mode="andon" />
      <ExceptionPanel apiBase={apiBase} mode="triage" />
    </>
  );
}
