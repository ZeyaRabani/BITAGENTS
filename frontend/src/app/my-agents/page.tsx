import type { Metadata } from "next";
import { YourAgentsPage } from "@/components/agents/builder/YourAgentsPage";

export const metadata: Metadata = {
  title: "My Agents - BITAGENTS",
  description: "Strategies you built on BITAGENTS.",
};

export default function MyAgentsPage() {
  return <YourAgentsPage />;
}
