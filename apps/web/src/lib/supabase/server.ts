import { cookies } from "next/headers";
import { createServerClient, type CookieOptions } from "@supabase/ssr";
import type { Database } from "@/types/database";

/**
 * Supabase client for use in Server Components, Server Actions, and Route
 * Handlers. Wires cookie read/write through Next.js's `cookies()` so the
 * user's session survives across server-rendered navigations.
 *
 * The `set`/`remove` calls are wrapped in try/catch because Server
 * Components are allowed to read cookies but not write them — this only
 * actually runs from a Server Action or Route Handler, where writing is
 * allowed; middleware.ts is what keeps the session refreshed for the
 * plain Server Component render path.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options);
            });
          } catch {
            // Called from a Server Component render — expected, no-op.
          }
        },
      },
    }
  );
}
