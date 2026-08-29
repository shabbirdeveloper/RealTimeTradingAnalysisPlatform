export function StatusDot({ status }: { status: "Healthy" | "Warning" | "Offline" }) {
  const cls = status === "Healthy" ? "bg-call" : status === "Warning" ? "bg-notrade" : "bg-put";
  return (
    <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
      <span className={`h-1.5 w-1.5 rounded-full ${cls}`} /> {status}
    </span>
  );
}
