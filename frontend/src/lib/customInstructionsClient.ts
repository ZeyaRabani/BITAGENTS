export async function getCustomInstructions(
  agentType: string,
  authToken: string
): Promise<string> {
  const res = await fetch(`/api/agents/custom-instructions/${encodeURIComponent(agentType)}`, {
    headers: { Authorization: `Bearer ${authToken}` },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to load custom instructions: ${text}`);
  }
  const data = (await res.json()) as { instructions: string };
  return data.instructions || "";
}

export async function saveCustomInstructions(
  agentType: string,
  instructions: string,
  authToken: string
): Promise<void> {
  const res = await fetch("/api/agents/custom-instructions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ agent_type: agentType, instructions }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to save custom instructions: ${text}`);
  }
}
