import {
  builderAuthRequired,
  getAuthToken,
  readJsonBody,
  relayBuilder,
} from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) return builderAuthRequired();
  return relayBuilder("/agents", { authToken });
}

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) return builderAuthRequired();
  const body = await readJsonBody(request);
  if (!body) return Response.json({ detail: "Invalid JSON body" }, { status: 400 });
  return relayBuilder("/agents", { method: "POST", body: { prompt: body.prompt }, authToken });
}
