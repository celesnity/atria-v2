import ConfigPanel from '../panels/ConfigPanel';
import SopPanel from '../panels/SopPanel';
import SetupPanel from '../panels/SetupPanel';
import OeePanel from '../panels/OeePanel';

export default function AdminRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <ConfigPanel apiBase={apiBase} />
      <SopPanel apiBase={apiBase} />
      <SetupPanel apiBase={apiBase} />
      <OeePanel apiBase={apiBase} />
    </>
  );
}
