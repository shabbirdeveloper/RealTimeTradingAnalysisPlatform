"use client";
import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { setAccess } from "@/app/admin/users/actions";
import type { AccessStatus } from "@/lib/admin";

/**
 * Approve / refuse buttons for one account.
 *
 * Self is disabled in the UI as well as refused by the database. The
 * database check is the one that matters; this one exists so an admin
 * never clicks a button that was only ever going to throw.
 */
export function AccessControls({
  userId,
  status,
  isSelf,
}: {
  userId: string;
  status: AccessStatus | null;
  isSelf: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  if (isSelf) {
    return <span className="text-xs text-muted-foreground">your account</span>;
  }
  if (status === null) {
    return <span className="text-xs text-muted-foreground">migration 18 not run</span>;
  }

  function apply(next: AccessStatus) {
    setError(null);
    startTransition(async () => {
      const result = await setAccess(userId, next);
      if (!result.ok) setError(result.error);
    });
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex gap-1.5">
        {status !== "APPROVED" && (
          <Button size="sm" disabled={pending} onClick={() => apply("APPROVED")}>
            Approve
          </Button>
        )}
        {status !== "REJECTED" && (
          <Button size="sm" variant="outline" disabled={pending} onClick={() => apply("REJECTED")}>
            {status === "APPROVED" ? "Revoke" : "Refuse"}
          </Button>
        )}
      </div>
      {error && <span className="text-[10.5px] text-destructive">{error}</span>}
    </div>
  );
}
