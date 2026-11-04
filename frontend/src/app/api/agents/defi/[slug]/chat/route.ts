import { handleDefiAgentChat } from "@/server/defiAgentRoutes";

export async function POST(
  request: Request,
  context: { params: Promise<{ slug: string }> }
) {
  const { slug } = await context.params;
  return handleDefiAgentChat(request, slug);
}
