import {
  builderAuthRequired,
  getAuthToken,
  readJsonBody,
  relayBuilder,
} from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const authToken = getAuthToken(request);
  if (!authToken) return builderAuthRequired();
  const body = await readJsonBody(request);
  if (!body) return Response.json({ detail: "Invalid JSON body" }, { status: 400 });
  return relayBuilder(`/agents/${encodeURIComponent(id)}/chat`, {
    method: "POST",
    body: {
      message: body.message,
      ...(typeof body.session_id === "string" ? { session_id: body.session_id } : {}),
    },
    authToken,
  });
}
