import WorkPanel from '../panels/WorkPanel';
import OeePanel from '../panels/OeePanel';
import HandoverPanel from '../panels/HandoverPanel';
import ScrapPanel from '../panels/ScrapPanel';
import ExceptionPanel from '../panels/ExceptionPanel';

export default function SupervisorRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <WorkPanel apiBase={apiBase} mode="load" />
      <OeePanel apiBase={apiBase} />
      <HandoverPanel apiBase={apiBase} />
      <ScrapPanel apiBase={apiBase} mode="hold" />
      <ExceptionPanel apiBase={apiBase} mode="escalated" />
    </>
  );
}
