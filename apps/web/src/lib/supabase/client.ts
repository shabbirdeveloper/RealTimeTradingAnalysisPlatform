import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "@/types/database";

/**
 * Supabase client for use in Client Components ("use client"). Reads the
 * public URL + anon key from env — safe to expose to the browser by design,
 * since every query still goes through this schema's RLS policies (see
 * supabase/migrations/20260829000008_rls_policies.sql). Never import the
 * service role key here.
 */
export function createClient() {
  return createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
