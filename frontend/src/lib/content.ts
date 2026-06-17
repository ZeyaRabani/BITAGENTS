export interface RoadmapPhase {
  phase: string;
  title: string;
  status: "live" | "in-progress" | "planned";
  items: string[];
}

export const ROADMAP: RoadmapPhase[] = [
  {
    phase: "Phase 1",
    title: "Launch",
    status: "in-progress",
    items: ["BITAGENTS token launch", "BIT10SOL holder airdrop", "Website and ecosystem setup"]
  },
  {
    phase: "Phase 2",
    title: "Hackathon MVP",
    status: "live",
    items: [
      "Wallet Watcher Agent",
      "Token Research Agent",
      "Market Research Agent",
      "Compute provider registration",
      "Solana devnet task payments"
    ]
  },
  {
    phase: "Phase 3",
    title: "Private Beta",
    status: "planned",
    items: ["Saved reports", "Watchlists", "Alerts", "Credits", "First early users"]
  },
  {
    phase: "Phase 4",
    title: "Public Beta",
    status: "planned",
    items: ["Subscriptions", "Token-holder premium access", "API access", "Compute provider dashboard"]
  },
  {
    phase: "Phase 5",
    title: "Marketplace",
    status: "planned",
    items: ["Third-party agents", "Provider staking", "Task routing", "Provider payouts"]
  },
  {
    phase: "Phase 6",
    title: "Automation",
    status: "planned",
    items: ["Transaction preparation", "Agent wallets", "User-approved execution"]
  }
];

export interface UtilityItem {
  title: string;
  body: string;
}

export const TOKEN_UTILITY: UtilityItem[] = [
  {
    title: "Premium agent access",
    body: "Token holding is designed to unlock premium agents and advanced report depth in future versions."
  },
  {
    title: "Higher usage limits",
    body: "Holders are planned to receive higher task and rate limits than free users."
  },
  {
    title: "Compute provider staking",
    body: "Providers may be required to stake tokens to register, signalling commitment and supporting reputation."
  },
  {
    title: "Agent creator staking",
    body: "Third-party agent creators may stake tokens to list agents once the marketplace opens."
  },
  {
    title: "Future discounted agent credits",
    body: "Future versions may let holders buy agent credits at a discount versus pay-as-you-go pricing."
  },
  {
    title: "Platform fees and planned buybacks",
    body: "A portion of platform fees is designed to fund planned buybacks. This is not a promise of revenue share or returns."
  }
];
