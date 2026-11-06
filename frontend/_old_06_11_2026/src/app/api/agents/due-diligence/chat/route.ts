import { handleResearchAgentChat } from "@/server/researchAgentRoutes";

export async function POST(request: Request) {
  return handleResearchAgentChat(request, "due-diligence");
}
