import { handleDefiAgentHealth } from "@/server/defiAgentRoutes";

export async function GET(
  _request: Request,
  context: { params: Promise<{ slug: string }> }
) {
  const { slug } = await context.params;
  return handleDefiAgentHealth(slug);
}
