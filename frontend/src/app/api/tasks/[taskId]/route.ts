import { readDb } from "@/server/db";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: { taskId: string } }) {
  const db = await readDb();
  const task = db.tasks.find((item) => item.id === params.taskId);
  if (!task) {
    return Response.json({ error: "task not found." }, { status: 404 });
  }
  return Response.json({ task });
}
