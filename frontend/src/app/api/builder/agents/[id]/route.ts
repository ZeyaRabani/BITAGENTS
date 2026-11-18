import { relayBuilder } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return relayBuilder(`/agents/${encodeURIComponent(id)}`);
}
