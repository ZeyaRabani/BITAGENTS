import { nowIso, type DcaChatMessage, type DcaExecution, type DcaPlan } from "@bitagents/shared";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

// ---------------------------------------------------------------------
// DCA data store with a pluggable backend.
//
//   * UPSTASH_REDIS_REST_URL (+ token) -> Upstash Redis (serverless-safe)
//   * DATABASE_URL                      -> Postgres (documented extension
//                                          point; falls back to JSON if no
//                                          driver is wired in this build)
//   * otherwise                         -> local JSON file (dev default)
//
// The whole document is small (a demo's worth of plans), so each backend
// reads/writes a single JSON blob. Writes are serialized in-process to avoid
// read-modify-write races within one server instance.
// ---------------------------------------------------------------------

export interface StoredAgentWallet {
  userWallet: string;
  publicKey: string;
  encryptedSecret: string;
  network: "mainnet" | "devnet";
  createdAt: string;
}

export interface ErrorLog {
  id: string;
  scope: string;
  message: string;
  at: string;
}

export interface DcaDb {
  plans: DcaPlan[];
  executions: DcaExecution[];
  chats: DcaChatMessage[];
  agentWallets: StoredAgentWallet[];
  errors: ErrorLog[];
  idempotencyKeys: string[];
}

const EMPTY_DB: DcaDb = {
  plans: [],
  executions: [],
  chats: [],
  agentWallets: [],
  errors: [],
  idempotencyKeys: []
};

interface Backend {
  label: string;
  read(): Promise<DcaDb>;
  write(db: DcaDb): Promise<void>;
}

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : undefined;
}

// ---- JSON file backend -------------------------------------------------

function dataDir(): string {
  if (process.env.BITAGENTS_DATA_DIR) return process.env.BITAGENTS_DATA_DIR;
  if (process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME) {
    return path.join(os.tmpdir(), "bitagents");
  }
  return path.join(process.cwd(), ".data");
}

const jsonBackend: Backend = {
  label: "json",
  async read() {
    try {
      const raw = await readFile(path.join(dataDir(), "bitagents-dca.json"), "utf8");
      return { ...structuredClone(EMPTY_DB), ...(JSON.parse(raw) as Partial<DcaDb>) };
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      return structuredClone(EMPTY_DB);
    }
  },
  async write(db) {
    const file = path.join(dataDir(), "bitagents-dca.json");
    await mkdir(path.dirname(file), { recursive: true });
    await writeFile(file, `${JSON.stringify(db, null, 2)}\n`, "utf8");
  }
};

// ---- Upstash Redis REST backend ---------------------------------------

const UPSTASH_KEY = "bitagents:dca";

function upstashBackend(url: string, token: string): Backend {
  async function command(args: (string | number)[]): Promise<unknown> {
    const response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(args)
    });
    if (!response.ok) throw new Error(`Upstash error (HTTP ${response.status}).`);
    const payload = (await response.json()) as { result?: unknown };
    return payload.result ?? null;
  }
  return {
    label: "upstash-redis",
    async read() {
      const result = (await command(["GET", UPSTASH_KEY])) as string | null;
      if (!result) return structuredClone(EMPTY_DB);
      return { ...structuredClone(EMPTY_DB), ...(JSON.parse(result) as Partial<DcaDb>) };
    },
    async write(db) {
      await command(["SET", UPSTASH_KEY, JSON.stringify(db)]);
    }
  };
}

function resolveBackend(): Backend {
  const upstashUrl = clean(process.env.UPSTASH_REDIS_REST_URL);
  const upstashToken = clean(process.env.UPSTASH_REDIS_REST_TOKEN);
  if (upstashUrl && upstashToken) {
    return upstashBackend(upstashUrl, upstashToken);
  }
  // DATABASE_URL (Postgres/Prisma) is a documented extension point. No driver
  // is bundled in this build, so we fall back to JSON and note it once.
  if (clean(process.env.DATABASE_URL)) {
    // eslint-disable-next-line no-console
    console.warn(
      "[dca] DATABASE_URL is set but no Postgres driver is wired in; using JSON store. See README."
    );
  }
  return jsonBackend;
}

let backend: Backend | null = null;
function getBackend(): Backend {
  if (!backend) backend = resolveBackend();
  return backend;
}

export function storeBackendLabel(): string {
  return getBackend().label;
}

let writeChain: Promise<unknown> = Promise.resolve();

/** Serialized read-modify-write against the active backend. */
export async function withDcaDb<T>(mutator: (db: DcaDb) => T | Promise<T>): Promise<T> {
  const run = async (): Promise<T> => {
    const b = getBackend();
    const db = await b.read();
    const result = await mutator(db);
    await b.write(db);
    return result;
  };
  const next = writeChain.then(run, run);
  // Keep the chain alive but don't let rejections break future writes.
  writeChain = next.catch(() => undefined);
  return next;
}

export async function readDcaDb(): Promise<DcaDb> {
  return getBackend().read();
}

// ---- High-level helpers ------------------------------------------------

export async function createPlan(plan: DcaPlan): Promise<DcaPlan> {
  return withDcaDb((db) => {
    db.plans.unshift(plan);
    return plan;
  });
}

export async function getPlan(id: string): Promise<DcaPlan | undefined> {
  const db = await readDcaDb();
  return db.plans.find((plan) => plan.id === id);
}

export async function listPlansByWallet(wallet: string): Promise<DcaPlan[]> {
  const db = await readDcaDb();
  return db.plans.filter((plan) => plan.userWallet === wallet);
}

export async function listActivePlans(): Promise<DcaPlan[]> {
  const db = await readDcaDb();
  return db.plans.filter((plan) => plan.status === "active");
}

export async function updatePlan(
  id: string,
  patch: Partial<DcaPlan> | ((plan: DcaPlan) => void)
): Promise<DcaPlan | undefined> {
  return withDcaDb((db) => {
    const plan = db.plans.find((item) => item.id === id);
    if (!plan) return undefined;
    if (typeof patch === "function") patch(plan);
    else Object.assign(plan, patch);
    plan.updatedAt = nowIso();
    return plan;
  });
}

export async function addExecution(execution: DcaExecution): Promise<DcaExecution> {
  return withDcaDb((db) => {
    db.executions.unshift(execution);
    return execution;
  });
}

export async function listExecutions(planId: string): Promise<DcaExecution[]> {
  const db = await readDcaDb();
  return db.executions
    .filter((execution) => execution.planId === planId)
    .sort((a, b) => a.orderIndex - b.orderIndex);
}

export async function appendChat(message: DcaChatMessage): Promise<void> {
  await withDcaDb((db) => {
    db.chats.push(message);
  });
}

export async function reserveIdempotencyKey(key: string): Promise<boolean> {
  return withDcaDb((db) => {
    if (db.idempotencyKeys.includes(key)) return false;
    db.idempotencyKeys.push(key);
    if (db.idempotencyKeys.length > 5000) db.idempotencyKeys.splice(0, 1000);
    return true;
  });
}

export async function saveAgentWallet(wallet: StoredAgentWallet): Promise<void> {
  await withDcaDb((db) => {
    const existing = db.agentWallets.findIndex((item) => item.userWallet === wallet.userWallet);
    if (existing >= 0) db.agentWallets[existing] = wallet;
    else db.agentWallets.push(wallet);
  });
}

export async function getAgentWallet(userWallet: string): Promise<StoredAgentWallet | undefined> {
  const db = await readDcaDb();
  return db.agentWallets.find((item) => item.userWallet === userWallet);
}

export async function logError(scope: string, message: string): Promise<void> {
  await withDcaDb((db) => {
    db.errors.unshift({ id: globalThis.crypto.randomUUID(), scope, message, at: nowIso() });
    if (db.errors.length > 500) db.errors.length = 500;
  });
}
