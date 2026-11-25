import { builderAuthRequired, getAuthToken, relayBuilder } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const authToken = getAuthToken(request);
  if (!authToken) return builderAuthRequired();
  return relayBuilder(`/agents/${encodeURIComponent(id)}/aomi`, { authToken });
}
