import { NextResponse } from "next/server";
import { proxyWaitlistSignup } from "@/server/agentsApiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type SignupBody = {
  email?: unknown;
  telegram?: unknown;
  twitter?: unknown;
  interest?: unknown;
  notify_when_ready?: unknown;
};

function asOptionalString(value: unknown) {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

export async function POST(request: Request) {
  let body: SignupBody;
  try {
    body = (await request.json()) as SignupBody;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const email = asOptionalString(body.email);
  const interest = asOptionalString(body.interest);
  if (!email) {
    return NextResponse.json({ error: "Email is required." }, { status: 400 });
  }
  if (!interest) {
    return NextResponse.json({ error: "Please select how you want to use BIT Agents." }, { status: 400 });
  }

  const upstream = await proxyWaitlistSignup({
    email,
    telegram: asOptionalString(body.telegram),
    twitter: asOptionalString(body.twitter),
    interest,
    notify_when_ready:
      typeof body.notify_when_ready === "boolean" ? body.notify_when_ready : true,
  });

  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : typeof data?.error === "string"
          ? data.error
          : `Signup failed (${upstream.status})`;
    return NextResponse.json({ error: detail }, { status: upstream.status });
  }
  return NextResponse.json(data, { status: upstream.status });
}
