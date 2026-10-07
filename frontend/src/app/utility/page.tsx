import { ArrowRight, Coins, Crown, Landmark, LockKeyhole, Repeat2, Sparkles } from "lucide-react";
import Link from "next/link";

const utilities = [
  {
    title: "Platform fees and buybacks",
    icon: Repeat2,
    text: "A future BITAGENTS token can capture marketplace fees and route a portion toward transparent buyback mechanics."
  },
  {
    title: "Compute provider staking",
    icon: LockKeyhole,
    text: "Providers can stake to signal reliability, unlock assignment tiers, and backstop service-level commitments."
  },
  {
    title: "Premium agent access",
    icon: Crown,
    text: "Token-gated agents can offer higher limits, specialized workflows, and advanced automation templates."
  },
  {
    title: "Marketplace settlement",
    icon: Landmark,
    text: "The MVP uses SOL on devnet, while the task and payout records are structured for token settlement later."
  },
  {
    title: "Future agent credits",
    icon: Coins,
    text: "Credits can make repeated agent runs smoother for users while keeping provider payouts auditable."
  },
  {
    title: "Composable agent economy",
    icon: Sparkles,
    text: "Agent developers, compute providers, and users can share one marketplace loop as the protocol expands."
  }
];

export default function UtilityPage() {
  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="max-w-3xl">
        <p className="text-sm font-black uppercase text-ember">Token utility roadmap</p>
        <h1 className="mt-2 text-3xl font-black text-white sm:text-5xl">BITAGENTS token utility</h1>
        <p className="mt-4 text-lg leading-8 text-slate-300">
          The hackathon MVP settles with SOL on Solana devnet for speed and clarity. The code keeps settlement, provider identity, and task history explicit so token utility can be layered in without changing the core marketplace loop.
        </p>
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {utilities.map(({ title, text, icon: Icon }) => (
          <div key={title} className="rounded-md border border-line bg-panel/80 p-5">
            <Icon className="text-ember" size={24} />
            <h2 className="mt-4 text-lg font-black text-white">{title}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-400">{text}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 rounded-md border border-line bg-ink/70 p-5">
        <p className="font-black text-white">Current MVP settlement</p>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">Users pay task fees to a configurable treasury public key. Provider payout can be sent from a connected treasury wallet in the demo page, or from the API when TREASURY_SECRET_KEY is configured for devnet.</p>
        <Link href="/demo" className="mt-4 inline-flex items-center gap-2 rounded-md bg-ember px-4 py-2 font-black text-ink transition hover:bg-coral">
          View demo flow <ArrowRight size={17} />
        </Link>
      </div>
    </section>
  );
}
