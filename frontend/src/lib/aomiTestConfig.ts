export const AOMI_TEST = {
  slug: "aomi-test",
  name: "Test Aomi Agent",
  tagline: "Aomi builds the transfer · Circle signs it",
  description:
    "A small test agent on Aomi. It sends SOL from its Circle address to another address. Aomi composes the transaction. Circle holds the key and signs.",
  assistantLabel: "Test Aomi",
  examplePrompts: [
    "Send 0.001 SOL to YourSolanaAddressHere",
  ],
} as const;
