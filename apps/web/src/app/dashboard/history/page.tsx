import { getSignalHistory } from "@/lib/history";
import { HistoryTable } from "@/components/dashboard/history-table";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const rows = await getSignalHistory();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Signal History</h1>
        <p className="text-sm text-muted-foreground">Every real signal the engine has generated — unresolved ones show as PENDING.</p>
      </div>

      <HistoryTable rows={rows} />
    </div>
  );
}
