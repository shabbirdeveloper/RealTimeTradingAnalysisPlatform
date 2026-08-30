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
 */
const PROTECTED_PREFIXES = ["/dashboard", "/admin"] as const;

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export async function middleware(request: NextRequest) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const { pathname: earlyPath } = request.nextUrl;

  if (!supabaseUrl || !supabaseAnonKey) {
    if (isProtected(earlyPath)) {
      // Cannot verify identity -> refuse. `error=config` distinguishes a
      // misconfigured deployment from an ordinary signed-out redirect, so
      // this doesn't get mistaken for a login loop.
      const loginUrl = new URL("/login", request.url);
      loginUrl.searchParams.set("error", "config");
      return NextResponse.redirect(loginUrl);
    }
    return NextResponse.next();
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
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isAdmin = pathname === "/admin" || pathname.startsWith("/admin/");

  if (isProtected(pathname) && !user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectedFrom", pathname);
    return NextResponse.redirect(loginUrl);
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
