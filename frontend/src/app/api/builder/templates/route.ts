import { relayBuilder } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return relayBuilder("/templates");
}
