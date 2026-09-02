"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import type { AccessStatus } from "@/lib/admin";

/**
 * Approve or refuse an account.
 *
 * The authorization lives in `admin_set_access()`, not here. A Server
 * Action is an HTTP endpoint like any other, so a check performed only in
 * this file would be a check performed only for callers who came through
 * this page. The function raises for non-admins, refuses to act on the
 * caller's own row, cannot touch `role`, and writes an audit_logs entry.
 */
export async function setAccess(
  userId: string,
  status: AccessStatus,
  note?: string
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const supabase = await createClient();
    const { error } = await supabase.rpc("admin_set_access", {
      target_user: userId,
      new_status: status,
      note: note ?? null,
    });
    if (error) return { ok: false, error: error.message };
    revalidatePath("/admin/users");
    revalidatePath("/admin");
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not update access." };
  }
}
