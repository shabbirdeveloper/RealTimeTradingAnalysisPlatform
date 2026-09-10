import { NextResponse, type NextRequest } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";

/**
 * Refreshes the Supabase auth session on every request that isn't a static
 * asset, and enforces the actual route protection for /dashboard and
 * /admin (spec section 38: "server-side role checks", not just a client
 * redirect).
 *
 * FAILS CLOSED. An earlier version returned NextResponse.next() when the
 * Supabase env vars were missing, on the reasoning that it should "no-op
 * safely" before a project was connected. That reasoning is inverted: a
 * security control whose configuration is absent must deny, not wave the
 * request through. It was verified in production that /dashboard and
 * /admin rendered fully for a request carrying no session cookies at all.
 *
 * Public routes still pass through when unconfigured, so the marketing
 * pages keep working; protected routes do not.
 *
 * AND IT MUST NEVER THROW. Middleware runs on EVERY request, so an
 * uncaught exception here is not a broken page -- it is
 * MIDDLEWARE_INVOCATION_FAILED on the entire site, marketing pages
 * included. Three things in the original could throw and none was
 * guarded: createServerClient on a malformed URL (a value pasted with
 * quotes or a stray space is enough), auth.getUser() on any network
 * trouble reaching Supabase, and destructuring `data.user` when `data`
 * came back undefined.
 *
 * Every failure now lands in the SAME place as "not configured": deny the
 * protected routes, let the public ones through. The security property is
 * unchanged -- an identity that cannot be verified is not trusted -- while
 * a Supabase hiccup stops taking the whole site down with it.
 */

/** Deny protected routes, serve public ones. The one response to every
 *  reason we cannot verify who is asking. */
function unverified(request: NextRequest, reason: string) {
  if (isProtected(request.nextUrl.pathname)) {
    const loginUrl = new URL("/login", request.url);
    // Distinguishes a misconfigured or unreachable deployment from an
    // ordinary signed-out redirect, so this is never read as a login loop.
    loginUrl.searchParams.set("error", reason);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}
// /pending is protected too: it reports YOUR status, so it needs a session.
// The approval gate below skips it explicitly, or a pending user would be
// redirected to it forever.
const PROTECTED_PREFIXES = ["/dashboard", "/admin", "/pending"] as const;

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export async function middleware(request: NextRequest) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const { pathname: earlyPath } = request.nextUrl;

  if (!supabaseUrl || !supabaseAnonKey) {
    return unverified(request, "config");
  }

  // A value pasted with surrounding quotes, a trailing space, or a missing
  // scheme parses as a URL nowhere -- and createServerClient throws on it,
  // which is one of the ways this middleware used to take the site down.
  try {
    new URL(supabaseUrl);
  } catch {
    return unverified(request, "config");
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });

  // Touches the session so an expired access token gets refreshed via the
  // refresh token before any Server Component tries to read it.
  //
  // Wrapped, and the result read defensively: this is a network call, and
  // an unwrapped rejection here was returning 500 for every page on the
  // site rather than for the one route that needed a session.
  let user: { id: string } | null = null;
  try {
    const result = await supabase.auth.getUser();
    user = result?.data?.user ?? null;
  } catch {
    return unverified(request, "unavailable");
  }

  const { pathname } = request.nextUrl;
  const isAdmin = pathname === "/admin" || pathname.startsWith("/admin/");

  if (isProtected(pathname) && !user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectedFrom", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Approval gate. A pending account holds a valid session, so without this
  // it would land on the dashboard like anyone else. Deliberately a single
  // query on the same row the admin check already needs.
  if (isProtected(pathname) && user) {
    try {
      const { data: profile } = await supabase
        .from("profiles")
        .select("role, access_status")
        .eq("id", user.id)
        .maybeSingle();

      const row = profile as { role?: string; access_status?: string } | null;
      // Admins are never held at the gate -- the console that approves
      // people must stay reachable. Anything other than APPROVED for a
      // non-admin waits, including a missing column on a database that
      // has not run migration 18 yet (undefined !== 'APPROVED'), which
      // fails closed rather than open.
      if (row?.role !== "admin" && row?.access_status !== "APPROVED") {
        if (pathname !== "/pending") {
          return NextResponse.redirect(new URL("/pending", request.url));
        }
      }
    } catch {
      return NextResponse.redirect(new URL("/pending", request.url));
    }
  }

  if (isAdmin && user) {
    // Fails closed: if the profiles table isn't reachable yet (e.g. the
    // migrations haven't been run against this project), nobody gets
    // treated as an admin rather than everybody.
    try {
      const { data: profile } = await supabase
        .from("profiles")
        .select("role")
        .eq("id", user.id)
        .maybeSingle();

      if (profile?.role !== "admin") {
        return NextResponse.redirect(new URL("/dashboard", request.url));
      }
    } catch {
      return NextResponse.redirect(new URL("/dashboard", request.url));
    }
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
