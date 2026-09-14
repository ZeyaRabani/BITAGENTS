# Marketplace testing status — answers to Harshal's two questions

Harshal's WhatsApp brief (13 Sept):

> So for Persistent memory, we can just store the user message and response in
> the DB, and send those response with current message to the agent. Then for
> the marketplace the issue which we need to solve is the API one, we would
> need API keys from specific tasks for example for looking up news, etc..
> for that we can just ask users to go and give us the key, we will encrypt
> and store in the DB. Then we can start running the test for the
> marketplace.

## 1. Persistent memory — already done, nothing to build

Checked the code before touching anything: `chat_sessions` / `chat_messages`
tables already exist (`agent/new/db.py`), and `load_chat_history()` /
`append_chat_messages()` are already wired into every chat route that
exists — DCA, Volume, and the custom launched-agent runtime. This is
already the exact shape described above and has been live for a while.
Nothing left to build here.

## 2. API keys — one thing to correct before building anything

Asking users to bring their own API key conflicts with BITAGENTS' actual
selling point: **zero setup for the end user.** Any tool an agent needs
(news lookup, etc.) should use a key BITAGENTS itself holds — the user only
ever describes what they want in chat, never connects an account or pastes
a key anywhere. Two ways to build that, both keeping every key
server-side:

- **One shared key per service, usage metered per agent internally** — no
  new vendor, fastest to ship, matches the "no setup" bar exactly.
- **An API gateway (Zuplo/Unkey/Portkey) minting a key per agent** — each
  agent gets its own real quota, but it's a new vendor relationship and an
  open question whether it cleanly handles proxying *out* to a third-party
  API, not just authenticating requests *in*.

Recommend building the shared-key version first regardless of which way
this ultimately goes — same core piece either path needs, and it's a
contained swap later if a gateway makes more sense at scale.

## 3. The actual blocker for "start running the test," found tonight

Before either of the above matters: **the conversational agent-builder
doesn't reliably save what it says it saved.** Ran a full launch
conversation end to end (DCA agent, 4 turns, ending in "confirm" / "yes")
and checked the database after — the AI replied with a complete, confident
"I've finalized and launched the agent" including full config, but zero
tool calls fired across all 4 turns. The database row was still
`status: draft`, empty name, empty handle, `enabled_tools: []`.

Root cause: `agent_builder.py` requests `openai/gpt-4o-mini`, but
`resolve_capix_model()` silently forces the platform-locked
`meta-llama/llama-3.1-8b-instruct` regardless of what's requested — and that
model isn't reliably emitting function calls for this task, it narrates the
outcome in prose instead. Tried overriding to `openai/gpt-4o-mini` and to a
larger Llama model directly against CapIX — both rejected
("Route temporarily unavailable") under the current provider pinning. This
needs an actual conversation with CapIX (Ruqa) about what's really available
on the account — not a code fix on our side.

**This blocks real end-to-end marketplace testing regardless of the API-key
question above** — an agent that can't reliably persist during creation
can't be trusted to run unattended later. Worth prioritizing over the API
key work.
