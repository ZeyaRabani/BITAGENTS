# Per-user agent wallets — architecture scoping ("Operation Multi-wallet")

Status: core primitives built and proven live on a local Solana network
(2026-08-12) — derivation, per-user index assignment, and fee-payer
sponsorship all confirmed working end-to-end with a real on-chain transaction.
**Not yet wired into any live deposit/withdrawal/execution flow.** See
`agent/new/agent_wallets.py` for the code and the "Proof so far" section below
for exactly what's been verified.

## Proof so far

Everything below was verified against a real, running Solana network — a local
`solana-test-validator` (identical transaction/RPC/fee semantics to devnet and
mainnet, just unrestricted and instant), not just reasoned through:

- **Per-user wallet index assignment** (`db.get_or_create_wallet_index`) — 20
  simultaneous requests for the same user always converge on the same index;
  15 different concurrent users never collide.
- **Wallet derivation** (`agent_wallets.derive_user_keypair`) — same
  seed+agent+index always yields the same wallet; different users, and the
  same user across different agents, always get different wallets.
- **Fee-payer sponsorship, proven with a real on-chain transaction**: airdropped
  test SOL to both a derived user wallet and a separate fee-payer wallet, sent
  a sponsored transfer, and confirmed on-chain that the user's wallet lost
  *exactly* the transfer amount and not one lamport more, while the fee payer
  covered the entire 10,000-lamport network fee. This is the core claim of
  the whole redesign — that per-user wallets don't need their own SOL for
  gas — and it's no longer theoretical.

Devnet itself couldn't be used directly for this (the public faucet was
rate-limited on this sandbox's shared IP, and its own site asked automated
tools not to use its web form) — a local validator gave an equivalent, and in
some ways stronger, proof: real transaction and fee mechanics, zero rate
limits, fully reproducible.

## The problem with the current model

Today, each agent (DCA, Volume, EasyA) has exactly one on-chain wallet, funded by an
env var private key (`DCA_WALLET_PRIVATE_KEY`, etc.). Every user who deposits sends
funds to that *same* address. The blockchain has no concept of "users" here — it
just sees one wallet. The only thing that knows who owns what is a Postgres ledger
(`user_ledger`) that sums deposit/spend/acquire/withdraw rows per wallet address.

This means the ledger *is* the entire security boundary between users. Any bug in
the ledger's accounting logic — like the withdrawal race we just fixed — is a bug
that can move money between users, or let someone withdraw more than they put in.
It also means one compromised private key drains every user's funds at once, which
is how most real hot-wallet exchange hacks have actually happened.

## The alternative: HD-derived per-user wallets

Give every user their own real Solana keypair, generated deterministically from one
master seed plus an index unique to that user. This is the same idea as a hardware
wallet deriving many addresses from one seed phrase — one secret to protect, an
unlimited number of independent wallets derivable from it on demand.

**This needs no new dependency.** `solders` — already in `requirements.txt`, already
used everywhere in this codebase — has `Keypair.from_seed_and_derivation_path(seed,
path)` built in, implementing the standard SLIP-0010 ed25519 derivation scheme
(the same one Phantom/Solflare/Ledger use). Verified directly:

```python
from solders.keypair import Keypair

def derive_user_keypair(master_seed: bytes, agent: str, wallet_index: int) -> Keypair:
    agent_slot = {"dca": 0, "volume": 1, "easya": 2}[agent]
    path = f"m/44'/501'/{agent_slot}'/{wallet_index}'"
    return Keypair.from_seed_and_derivation_path(master_seed, path)
```

Confirmed by direct test: the same `(master_seed, agent, wallet_index)` always
produces the same keypair, different users produce different keypairs, and the same
user produces a *different* wallet per agent (so a bug in one agent's wallet
handling can't touch another agent's funds for the same user). `501` is Solana's
registered SLIP-44 coin type — this is the real, standard path shape, not something
invented for this doc.

The consequence that matters: **you never store a private key per user.** You store
one master seed (properly secured — see below) and one small integer per user (which
agent-wallet index they've been assigned). The keypair itself is re-derived on demand,
every time it's needed, and thrown away after use.

## Why this is safer, not just different

- **Blast radius.** A ledger accounting bug can now only affect one user's own
  wallet — Solana's own runtime refuses to let a wallet send more than it holds, so
  even the exact class of bug we just fixed becomes, at worst, a rejected duplicate
  transaction rather than a drained pool.
- **No single point of total failure.** Compromising the master seed is still bad —
  but it requires deriving and draining each user's wallet individually (detectable,
  rate-limitable, slower), not one instant sweep of a fully-loaded pooled wallet.
- **The ledger becomes a display/audit layer, not the security boundary.** The
  on-chain balance of a user's own wallet is now the source of truth. The ledger can
  still exist for UX (transaction history, "your balance" displays) but a bug in it
  can no longer directly cause fund loss the way it could before.

## What has to change, concretely

**Deposits** — instead of showing every user the same agent wallet address, show
each user their own derived deposit address. Verification changes from "did a
transfer land in the shared wallet" to "did a transfer land in *this user's*
derived wallet" — actually simpler, since there's no need to disambiguate whose
deposit a given transaction was (today's `verify_and_record_deposit` has to match
a signature to a specific user; with per-user addresses, the address itself tells
you whose deposit it is).

**Withdrawals** — become dramatically simpler and structurally safer. Instead of
computing a derived "withdrawable" balance from a multi-table ledger aggregate
(today's approach, and the thing the race condition exploited), you check the
*actual on-chain balance* of that one user's wallet — a single RPC call — and send
from it. There's no ledger-vs-reality gap to race, because the wallet only ever
holds that one user's funds.

**DCA/Volume/EasyA scheduled execution** — the schedulers (already fixed this
session to claim jobs safely across instances) need to derive the correct signing
keypair for each plan's owning user at execution time, instead of using one shared
agent keypair. This is a small, contained change — the scheduler already looks up
`plan["user_wallet"]` for every job; deriving `derive_user_keypair(master_seed,
agent, wallet_index_for(user_wallet))` right before signing is a natural fit into
that existing flow.

**Transaction fees — the fee-payer pattern.** You do *not* need to fund 100k
individual wallets with SOL for gas. Solana transactions have a fee payer field
that's independent of who authorizes the actual transfer. The standard pattern
(confirmed against [Privy's gas sponsorship docs](https://docs.privy.io/wallets/gas-and-asset-management/gas/solana),
a real wallet-infrastructure provider using exactly this design): one small,
separate operational wallet holds SOL and pays the network fee for every
transaction, while the user's own derived wallet only ever needs to authorize the
transfer of *their* funds — it never needs its own SOL balance for gas. This means
exactly one wallet needs topping up and monitoring, not 100k. Their security
guidance is directly relevant here too: always verify a transaction's instructions
before co-signing as fee payer, to make sure nothing tries to drain the fee-payer
wallet itself.

**Token account rent — a real, already-known cost, not a new problem.** Every SPL
token a wallet holds needs an Associated Token Account, which requires a small
rent-exempt SOL deposit. This cost already exists in the current pooled model — it's
`ATA_RENT_SOL = 0.00204` (defined in `volume_ledger.py`, already a live constant in
this codebase). The only change is that it's now paid per `(user, token)` pair
instead of once per token globally, since each user has their own account instead
of sharing one. Real cost, worth knowing, not a blocker — the same order of
magnitude as what's already budgeted for today.

## Master seed custody

This is the one piece that needs real care, and honestly deserves its own
follow-up rather than a quick answer here. At minimum: the 64-byte seed should not
sit in a plain `.env` file the way `DCA_WALLET_PRIVATE_KEY` does today — it should
live in a proper secrets manager (Render's env vars are encrypted at rest but a
single leak still compromises everything; a dedicated KMS/HSM-backed signing
boundary would be the stronger version of this, where the raw seed never leaves a
secure enclave and only ever signs pre-built transactions). Worth scoping as its
own piece once the rest of this design is agreed on, not something to rush.

## Migration — do not attempt a live sweep of everyone's existing pooled funds

Existing users' balances currently sit in the single shared wallet, tracked by the
ledger. Migrating that in one shot (sweeping every user's ledger-computed balance
to their new derived wallet in a batch of transactions) is high-stakes and not
recommended as a first move — it multiplies exactly the kind of ledger-accuracy
assumption that caused the original problem, at the exact moment you'd want to be
most careful.

Better path: **new deposits go to per-user derived wallets from day one; the
existing pooled balance winds down naturally** as current users withdraw or spend
through the old path, which keeps working unmodified during the transition. Once
the pooled wallet's balance is negligible, it can be retired. No big-bang migration,
no moment where a bug could move a large batch of real user funds at once.

## Recommended sequencing

This is a real, meaningfully bigger project than anything done so far this session —
it touches deposits, withdrawals, every agent's execution path, and needs its own
careful testing before real funds move through it (following the same pattern used
for everything else this session: build and prove correctness against real
infrastructure before trusting it, not just reasoning about it). Suggested order:

1. ~~Prototype the derivation + fee-payer flow end-to-end with a couple of test
   accounts.~~ Done — see "Proof so far" above.
2. Design and review master seed custody properly — this is the piece with the
   least room for a mistake, and hasn't been started.
3. Wire new deposits through per-user wallets for one agent first (DCA is the
   natural pick — most-used, best understood), running alongside the existing
   pooled path.
4. Only after that's proven live, extend to Volume and EasyA, and let the old
   pooled wallets wind down.

This doc is meant as the starting point for that conversation with Harshal, not a
final design — worth reviewing together before anything here gets built.
