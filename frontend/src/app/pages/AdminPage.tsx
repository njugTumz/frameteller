import { AdminConsole } from '../../features/admin/components/AdminConsole'
import { useAdmin } from '../../features/admin/hooks/useAdmin'

export function AdminPage() {
  const a = useAdmin()
  return <AdminConsole overview={a.overview} entries={a.entries} error={a.error} onAct={(id, action) => void a.act(id, action)} onWatch={a.watch} onReserve={(usd) => void a.lowerReserve(usd)} />
}
