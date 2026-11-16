import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign up - BIT Agents",
  description:
    "Join the BIT Agents waitlist. Get notified when marketplace and agent-builder features ship.",
};

export default function SignupLayout({ children }: { children: React.ReactNode }) {
  return children;
}
