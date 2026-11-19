# BIT Agents - Platform Blueprint & Future Plan

**Status:** Living blueprint  
**Scope:** Agent marketplace on Solana, built on Aomi for agent runtime and on-chain transaction gating  
**Related docs:** `AGENTS.md`, `agent/new/AOMI.md`, `docs/PAYMENTS.md`, `agent/new/COMPLIANCE.md`

---

## 1. Vision

BIT Agents is an **AI agent marketplace** where anyone can:

1. Describe the agent they want in natural language.
2. Have that agent **built and run on Aomi**.
3. Execute **real Solana transactions** only after Aomi stages and simulates them.
4. Publish the agent as private, public/free, or paid.
5. Earn when other users subscribe to or use their agent.
6. Grow from simple trading bots into **general Solana co-pilots** (any on-chain task the platform can safely expose).

Aomi is the **agent runtime and transaction gate**. BIT Agents owns the **marketplace, custody (Circle), strategy logic, fees, and UI shell**. Where Aomi does not yet expose a capability, BIT Agents builds that capability as a backend skill or service and plugs it into Aomi via tools/APIs.

---

## 2. Design Principles

| # | Principle | Meaning |
|---|-----------|---------|
| 1 | **Aomi for every agent** | Chat, scheduling, skills, and on-chain staging/simulate/commit go through Aomi. |
| 2 | **BIT Agents for product surface** | Marketplace, wallets, fees, listings, and the shared UI live in Next.js + Python. |
| 3 | **Build what is missing** | If a skill or venue action is not available in Aomi, implement it in our backend and expose it as an Aomi-callable tool. |
| 4 | **One UI language** | Every agent (built-in or user-created) uses the same console pattern: chat, wallet strip, actions, confirmations, run log. |
| 5 | **Creator economy** | Creators can price agents; platform takes a cut on creation, usage, and transaction fees. |
| 6 | **Simulate before sign** | No live spend without Jupiter (or other venue) build → Aomi stage → simulate → commit → Circle sign → broadcast. |
| 7 | **Paper first** | New custom strategies default to paper; live is an explicit switch. |
| 8 | **Not financial advice** | Compliance copy and risk gates stay in product flows; they do not replace real risk code. |

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Product Surface                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Next.js marketplace                                                        │
│  - Discover agents  │  Launch Agent (composer)  │  My Agents / listings     │
│  - Shared Agent Console UI (chat · wallet · actions · confirm · run log)    │
│  - Wallet SIWS auth · deposits · pricing · public/private toggles           │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ /api/agents/* proxies
                                    v
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BIT Agents Strategy API (Python)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Auth / sessions     │  Agent builder        │  Built-in agents             │
│  Custody (two paths, │  Spec compose/compile │  DCA · Hedge · Sniper · …    │
│  see below)          │  Paper + live evaluate│  Schedulers                  │
│  Fee ledger / sweep  │  Marketplace catalog  │  Keep-alive / health         │
│  Capability plugins  │                       │                               │
└───────────┬───────────────────────┬───────────────────────┬─────────────────┘
            │                       │                       │
            │ tools / HTTP          │ SIWS + pipeline       │ Jupiter / RPC
            v                       v                       v
┌───────────────────────┐ ┌─────────────────────────────┐ ┌───────────────────────┐
│  Aomi (runtime)       │ │  Aomi SVM pipeline          │ │  Solana + venues      │
│  - Chat / skills      │ │  - stage                    │ │  - Jupiter swaps      │
│  - Hosted apps        │ │  - simulate (fork)          │ │  - SPL / programs     │
│  - Schedules          │ │  - commit                   │ │  - future: DeFi, NFTs │
│  - Agent wallets UX   │ │                              │ │  - xStocks / oracles  │
│                       │ │  Legacy built-ins (DCA ·    │ │                       │
│                       │ │  Volume · Hedge · Sniper):  │ │                       │
│                       │ │  Circle signs after commit  │ │                       │
│                       │ │                              │ │                       │
│                       │ │  Agent builder (new):       │ │                       │
│                       │ │  Aomi/Para agent wallet      │ │                       │
│                       │ │  signs directly - no        │ │                       │
│                       │ │  Circle step                │ │                       │
└───────────────────────┘ └─────────────────────────────┘ └───────────────────────┘
            │
            v
┌─────────────────────────────────────────────────────────────────────────────┐
│  Data: PostgreSQL (Neon) · agent specs · paper books · fees · waitlist      │
└─────────────────────────────────────────────────────────────────────────────┘
```

Two custody paths exist today, not one. Built-in agents created before the Aomi
agent-builder (DCA, Volume, Hedge, Sniper) still sign through Circle, with Aomi
only staging and simulating. Agents made through the Aomi agent-builder are
custodied and signed by an Aomi/Para agent wallet directly - Circle is never in
that path. Existing Circle-custodied users are not forced to move; see section
9 (Current State -> Target State) for the migration stance.

### Layer responsibilities

| Layer | Owns | Does not own |
|-------|------|--------------|
| **Frontend** | UX, listing, composer, shared console, wallet connect | Keys, fee math, swap building |
| **Python API** | Specs, fees, evaluation, plugs for missing skills | Browser UI, Aomi core runtime, agent-builder custody |
| **Aomi** | Agent chat, skills packaging, schedule, tx stage/sim/commit, and wallet custody + signing for agent-builder agents | Marketplace pricing, custody for legacy built-in agents |
| **Circle** | Per-agent wallets, message + tx signing, for legacy built-in agents (DCA, Volume, Hedge, Sniper) only | Strategy decisions, agent-builder custody |
| **Venues / RPC** | Quotes, chain state, broadcast after sign | Agent intent |

---

## 4. Agent Blueprint (canonical shape)

Every agent on the platform - built-in or user-created - conforms to the same contract.

### 4.1 Conceptual model

```
┌──────────────────────────────────────────────────────────────────┐
│                         Agent Instance                           │
├──────────────────────────────────────────────────────────────────┤
│  identity: id, slug, name, owner_wallet, visibility, price       │
│  runtime:  aomi_app / skill / hosted_app_ref                     │
│  mode:     paper | live                                          │
│  custody:  Circle agent wallet (legacy built-ins) or             │
│            Aomi/Para agent wallet (agent builder) - per user     │
│            × agent type/instance, never mixed within one agent   │
│  capability_set: tools the agent may call                        │
│  limits:   spend caps, slippage, schedule, compliance hooks      │
│  ui:       Shared Agent Console (same shell for all agents)      │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Lifecycle

```
Describe intent (NL)
        │
        v
 Compose spec (LLM → structured AgentSpec)
        │
        v
 Validate (templates, limits, compliance)
        │
        v
 Compile / publish to Aomi (hosted app or local skill)
        │
        v
 List privately  ──or──  Publish (free / priced)
        │
        v
 Run (paper evaluate or live stage→sim→commit→sign)
        │
        v
 Settle fees (creation · usage · tx cuts)
```

### 4.3 AgentSpec (logical fields)

```text
AgentSpec
- name, description
- strategy.template          # e.g. signal_basket@1, trigger_basket@1, custom@…
- strategy.params            # template-specific
- strategy.schedule_minutes
- limits                     # quote, max daily, slippage_bps, position caps
- capabilities[]             # declared tools: swap, transfer, read_wallet, …
- visibility                 # private | unlisted | public
- pricing                    # null | { amount_sol, period: one_time|monthly }
- mode                       # paper | live
```

### 4.4 Execution path (live)

```
User / schedule trigger
        │
        v
 Strategy evaluate (BIT Agents)
        │  orders?
        v
 Venue build (e.g. Jupiter unsigned swap for Circle payer)
        │
        v
 Aomi stage → simulate → commit
        │  fail → skip; never sign
        v
 Circle signs committed tx
        │
        v
 Broadcast + confirm on Solana
        │
        v
 Fee accrual + run log
```

Paper mode uses the same venue builds where possible, but **simulates** on mainnet state and books fills to a paper ledger - nothing is staged for signing.

---

## 5. Aomi Integration Blueprint

### 5.1 Roles of Aomi

| Concern | How Aomi is used |
|---------|------------------|
| **Building agents** | Compose skills / hosted apps from specs (`AOMI_HOSTED_APP`, Rust `aomi-app`, `.aomi/config.json`). |
| **Running agents** | Chat, tools, schedules live in Aomi; tools call BIT Agents HTTP APIs. |
| **On-chain safety** | `svm/stage` → `svm/simulate` → `svm/commit` before any Circle signature. |
| **UX for wallets** | Hosted chat can own agent wallet flows when local Aomi stack is not required. |

### 5.2 What BIT Agents builds and plugs into Aomi

When Aomi does not natively offer a capability, we implement it and expose it as a tool:

| Gap | BIT Agents plug | Exposed to Aomi as |
|-----|-----------------|--------------------|
| Recurring DCA plans | `dca_agent` + `/strategies` | Skill tools |
| Hedge / sniper sized swaps | `market_agents` | Chat tools + gate |
| Multi-name xStock baskets | `agent_builder` strategies | Hosted evaluate / run |
| Circle custody + SIWS for pipeline | `circle_*` + `aomi_pipeline` | Session behind gate |
| Marketplace listing & fees | catalog + ledger | Metadata / paywall APIs |
| Oracles / Yahoo / covenant risk | builder market + compliance modules | Strategy evaluate |
| Future: NFT, lending, staking, alerts | New capability modules | New tools in shared registry |

**Rule:** Prefer extending the **capability registry** over inventing a one-off agent UI or one-off signing path.

### 5.3 Capability registry (target)

```
Capability
- id: "solana.swap.jupiter"
- risk: spend
- requires: aomi_gate, circle_wallet
- input_schema / output_schema
- handler: python module
- aomi_tool_name: execute_swap
```

Agents declare which capabilities they may use. The shared console only surfaces actions those capabilities can produce.

---

## 6. Unified UI Blueprint

All agents share one console composition. Built-in pages (DCA, Hedge Fund, Sniper) and custom agents (`/agents/custom/[id]`, Launch / My Agents) must feel like the same product.

### 6.1 Shared Agent Console layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Header: Agent name · mode (paper/live) · visibility · price    │
├──────────────────────────────┬──────────────────────────────────┤
│  Chat                        │  Side rail                       │
│  - intro                     │  - Agent wallet + balance        │
│  - user / assistant turns    │  - Limits / schedule             │
│  - confirmation dialogs      │  - Capability chips              │
│  - suggested prompts         │  - Recent actions / txs          │
│                              │  - Run log / paper equity        │
├──────────────────────────────┴──────────────────────────────────┤
│  Composer input + send                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 UI invariants

- Same auth (wallet SIWS → bearer).
- Same action model (tool name, args, result, explorer links).
- Same confirm dialog for spend.
- Same empty states and error shapes.
- Launch Agent and My Agents reuse builder + console, not a separate design system.
- Marketplace cards (including Create Agent) stay consistent with directory filters.

### 6.3 Create / Launch flow UI

1. Marketplace **Create Agent** card → `/launch-agent`.
2. Natural-language brief → compose → reviewable spec → compile.
3. Success → My Agents → open Shared Console.
4. Optional publish: visibility + price → listing appears in marketplace.

---

## 7. Marketplace & Creator Economy

### 7.1 Visibility

| Visibility | Behavior |
|------------|----------|
| **Private** | Only owner. Default for new builds. |
| **Unlisted** | Accessible by link; not in directory. |
| **Public** | Listed in marketplace; free or paid. |

### 7.2 Pricing

Creators may:

- Keep the agent free.
- Set a **one-time** unlock price (SOL).
- Set a **subscription** (e.g. SOL / month).
- Change price or take private later (existing subscribers handled by clear rules).

### 7.3 Who can use whose agent

```
Creator publishes public agent
        │
        v
 Buyer discovers in marketplace
        │
        v
 Pay (if priced) → agent payment wallet
        │
        v
 Access granted → buyer runs agent under their own Circle custody
        │  (strategy logic from creator; funds stay with buyer)
        v
 Platform cut + creator withdrawable balance
```

**Important:** Using someone else's agent means using their **logic / skill**, not depositing into the creator's trading wallet (unless a future product explicitly offers pooled funds with separate compliance).

---

## 8. Fee Model (platform)

Aligned with `docs/PAYMENTS.md`. Blueprint summary:

### 8.1 Revenue streams

| Stream | When | Destination |
|--------|------|-------------|
| **Agent creation / launch fee** | User creates / launches a custom agent | `LAUNCH_FEE_WALLET` (100%) |
| **Platform cut on agent usage** | Buyer pays for a public paid agent | 10% platform / 90% creator (example split) |
| **Transaction / execution fees** | Live swaps or strategy fills | Accrue in agent wallet; monthly sweep to treasury |
| **Future: capability fees** | Premium tools (data, co-pilot seats) | Platform or shared with tool providers |

### 8.2 Fee flow diagram

```
┌──────────────┐   launch fee    ┌──────────────────┐
│ Creator      │ ──────────────► │ LAUNCH_FEE_WALLET│
└──────────────┘                 └──────────────────┘

┌──────────────┐  subscription   ┌──────────────────┐
│ Buyer        │ ──────────────► │ Agent pay wallet │
└──────────────┘                 │  90% creator     │
                                 │  10% platform    │──monthly──► TREASURY
                                 └──────────────────┘

┌──────────────┐  live tx fee    ┌──────────────────┐
│ Agent wallet │ ──────────────► │ Accrued pot      │──monthly──► TREASURY
└──────────────┘                 └──────────────────┘
```

### 8.3 Policy knobs (config, not hard-coded forever)

- `LAUNCH_COST_SOL`
- Platform % on creator sales
- Per-agent execution fee bps
- Monthly sweep buffer / min net (see PAYMENTS.md)
- Fee waivers for hackathon / paper-only agents

---

## 9. Current State → Target State

### 9.1 What exists today (MVP spine)

| Area | Status |
|------|--------|
| Next.js marketplace shell | Live |
| Wallet auth + Circle custody | Live (legacy built-ins: DCA / Volume / Hedge / Sniper) |
| Aomi/Para agent wallet custody + direct signing | Live (agent-builder agents only, via `aomi_bridge`) |
| Aomi pipeline gate for swaps | Live (`aomi_pipeline`) |
| DCA agent UI + strategy API | Live |
| Hedge Fund / Sniper (SOL↔token via Aomi gate) | Live |
| Agent builder (compose / compile / paper / live) | Ported; hosted Aomi path |
| Launch Agent / My Agents | Wired to builder |
| Payments model doc | Documented |
| Full creator marketplace UX (price, public listing, buy) | Partial / planned |
| Non-trading Solana co-pilot skills | Planned |
| Single Shared Console component for all agents | In progress (patterns exist; unify further) |

### 9.2 Target state

- Every agent path is Aomi-backed for chat and for spend.
- Creators ship public/paid agents from Launch Agent without custom code.
- Capability registry lets us add Solana actions without new UIs.
- Platform fees are automatic, auditable, and swept on schedule.
- Users treat BIT Agents as the place to **build, sell, and run** Solana agents - trading first, then everything else.

---

## 10. Future Plan

### Phase 0 - Harden the Aomi spine (now)

- Keep DCA, Hedge, Sniper, and builder on the same gate.
- Fix agent chat fallbacks so tools always answer (wallet, redirects).
- Hosted compile path stable without local Rust for demos.
- Unified console props for built-in vs custom agents.

### Phase 1 - Creator marketplace

- Public / private / price on My Agents.
- Agent payment wallets + 90/10 split.
- Directory filters: free, paid, category, creator.
- Launch fee enforcement on create.
- Usage metering (runs / month) for subscriptions.

### Phase 2 - Capability platform

- Formal capability registry + allowlists per agent.
- First non-swap capabilities: wallet read, token research, alerts, transfers with limits.
- “Missing in Aomi” modules shipped as BIT Agents tools, registered into Aomi skills.
- Paper + live toggles for every spend capability.

### Phase 3 - Beyond trading

- Co-pilot agents: talk through a trade, simulate, then confirm.
- Task agents: stake, unstake, NFT list/buy (gated), governance votes, limit orders.
- Multi-step workflows (plan → review → execute chain of actions).
- Templates marketplace: creators sell specs + prompts, not only live runners.

### Phase 4 - Earn at scale

- Creator dashboards (revenue, subscribers, run quality).
- Reputation / reviews for public agents.
- Featured listings; optional revenue share campaigns.
- Programmatic API for power creators to publish versions.

### Phase 5 - General Solana agent OS

- User prompt: “Build an agent that …” → any allowed capability set.
- From simple one-shot trade agents to long-running co-pilots.
- Cross-agent composition (agent A calls agent B under policy).
- Optional compute marketplace hook (providers run heavy evaluation; still Aomi-gated for spend).

---

## 11. Example User Journeys

### Journey A - User creates a trading basket

1. Opens **Launch Agent**.
2. Types: “Paper strategy on XOM and JPM, 6 month horizon, $100.”
3. Composer produces `signal_basket@1` spec; user compiles.
4. Agent appears in **My Agents** (paper).
5. User tests runs; switches to live when ready.
6. Live runs stage swaps through Aomi; Circle signs after commit.

### Journey B - Creator monetizes

1. Same as A, then sets visibility **public**, price **0.01 SOL / month**.
2. Pays launch fee (if enabled).
3. Buyers find listing → pay → unlock.
4. Creator withdraws 90%; platform sweeps 10%.

### Journey C - Non-trading co-pilot (future)

1. User: “Build an agent that watches my wallet, warns on large outflows, and can revoke a bad approval after I confirm.”
2. Spec selects capabilities: `wallet.read`, `alerts.push`, `token.revoke` (confirm-gated).
3. Aomi hosts chat + schedule; BIT Agents implements revoke + Aomi gate for the spendless or spendful tx as required.
4. Same Shared Console UI.

---

## 12. Data Model (target additions)

```text
agents
- id, owner_wallet, name, slug
- spec (jsonb), build (jsonb), build_status
- mode (paper|live)
- visibility (private|unlisted|public)
- price_sol, price_period
- aomi_app_ref
- created_at, updated_at

agent_entitlements
- agent_id, buyer_wallet
- status (active|expired|cancelled)
- paid_through, last_payment_sig

agent_payment_wallets
- agent_id, circle_address
- creator_withdrawable, platform_accrued

capability_grants
- agent_id, capability_id, enabled

fee_events
- id, kind (launch|usage|tx)
- agent_id, wallet, amount_sol, meta, created_at
```

(Exact migrations follow existing Neon / Drizzle conventions; ask before schema changes.)

---

## 13. Security & Compliance Guardrails

- Aomi simulate/commit required for live spend.
- Circle keys never exposed to frontend or Aomi as long-term custodians of user intent alone.
- Paper default; live requires explicit mode switch + confirmations.
- Capability allowlists prevent a “do anything” prompt from gaining unchecked spend tools.
- Compliance rules for quant templates remain code-enforced (`COMPLIANCE.md`), not prompt-only.
- Disclaimers in chat; no claim of financial advice.
- No secrets in `NEXT_PUBLIC_*`.

---

## 14. Success Metrics

| Metric | Why it matters |
|--------|----------------|
| % of live txs that passed Aomi gate | Safety of the spine |
| Agents created / week | Builder product-market fit |
| Public agents listed & paid unlocks | Creator economy |
| Share of runs on Shared Console | UI consistency |
| Non-trading capabilities used | Progress beyond trading |
| Creator payout volume | Earn loop health |
| Time from brief → first paper run | Friction of create flow |

---

## 15. Open Decisions

- Exact default launch fee and usage split in production.
- Whether pooled / managed strategies are ever offered (separate legal and custody design).
- Hosted Aomi vs self-hosted skill packaging for all creator agents.
- Ranking algorithm for marketplace (quality vs recency vs revenue).
- How far “any Solana action” goes before requiring formal audits per capability.

---

## 16. One-Page Summary

**BIT Agents = Marketplace + custody + fees + shared UI.**  
**Aomi = Agent build/runtime + on-chain simulation gate.**  
**Creators describe agents → we compile to Aomi → users run with Circle wallets → platform takes creation, usage, and tx cuts.**  
**Today: trading-focused agents.**  
**Tomorrow: any Solana task, from a one-click swap bot to a full trading co-pilot, with creators earning when others use what they built.**

---

*This document is the product blueprint. Implementation details may change; principles in §2 and the Aomi gate in §5 should not.*
