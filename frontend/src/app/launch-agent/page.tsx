import type { Metadata } from "next";
import { AgentComposer } from "@/components/agents/builder/AgentComposer";

export const metadata: Metadata = {
  title: "Create an agent - BITAGENTS",
  description:
    "Describe a trading strategy in plain words, compose its spec, and deploy it to Aomi.",
};

export default function LaunchAgentPage() {
  return <AgentComposer />;
}
