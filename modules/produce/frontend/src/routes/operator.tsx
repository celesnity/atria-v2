import WorkPanel from '../panels/WorkPanel';
import SopPanel from '../panels/SopPanel';
import WipPanel from '../panels/WipPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ScrapPanel from '../panels/ScrapPanel';

export default function OperatorRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <WorkPanel apiBase={apiBase} mode="queue" />
      <SopPanel apiBase={apiBase} />
      <WipPanel apiBase={apiBase} />
      <DowntimePanel apiBase={apiBase} mode="log" />
      <ScrapPanel apiBase={apiBase} mode="record" />
    </>
  );
}
