import { NextResponse, type NextRequest } from "next/server";

/**
 * A cheap early redirect for protected routes. NOTHING ELSE.
 *
 * WHY THIS IS NOW SO SMALL
 *
 * It used to create a Supabase client and verify the session here. That
 * put @supabase/ssr inside the Edge runtime, where it failed to load --
 * and because middleware runs on EVERY request, a module that fails to
 * load returns 500 for the entire site, landing page included. Three
 * attempts to guard it from within could not help: a try/catch inside a
 * function cannot catch the module that function lives in failing to
 * import.
 *
 * So the verification moved to where it belongs. app/dashboard/layout.tsx
 * and app/admin/layout.tsx are server components on the Node runtime,
 * with no such constraint, sitting closer to the data they protect. Each
 * calls getUser(), reads the profile, and redirects. THOSE are the checks
 * that decide.
 *
 * This file now only answers "is there any session cookie at all?" so a
 * signed-out visitor gets bounced before a page renders. It is an
 * optimisation, not the security boundary -- and it imports nothing but
 * next/server, so it cannot take the site down.
 *
 * Do not put authentication back in here.
 */

const PROTECTED_PREFIXES = ["/dashboard", "/admin", "/pending"] as const;

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Supabase stores its session in cookies named `sb-<project-ref>-auth-token`,
 * sometimes chunked with a `.0`, `.1` suffix. Matching the shape rather
 * than an exact name means this keeps working if the project ref changes,
 * and needs no environment variable to do it.
 *
 * A present cookie is NOT proof of a valid session -- it may be expired or
 * forged. That is fine: this only decides whether to skip rendering a page
 * the layout would refuse anyway. The layout does the real check.
 */
function hasSessionCookie(request: NextRequest): boolean {
  return request.cookies.getAll().some(
    (cookie) => cookie.name.startsWith("sb-") && cookie.name.includes("auth-token")
  );
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (isProtected(pathname) && !hasSessionCookie(request)) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirectedFrom", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
