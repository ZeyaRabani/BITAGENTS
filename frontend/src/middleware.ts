import { NextRequest, NextResponse } from "next/server";
import { isMaintenanceWindow } from "@/lib/maintenanceWindow";

export function middleware(request: NextRequest) {
  if (!isMaintenanceWindow()) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname === "/maintenance" ||
    pathname.match(/\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map|txt|xml)$/)
  ) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json(
      {
        error: "BIT Agents is under scheduled maintenance. Please try again after 2:30 PM IST.",
        maintenance: true,
        until_ist: "2026-09-10T14:30:00+05:30",
      },
      { status: 503, headers: { "Retry-After": "5400" } }
    );
  }

  const url = request.nextUrl.clone();
  url.pathname = "/maintenance";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
