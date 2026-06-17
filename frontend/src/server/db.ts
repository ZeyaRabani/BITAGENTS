import {
  DEFAULT_TASK_PRICE_SOL,
  nowIso,
  type AgentTask,
  type BitagentsDb,
  type ComputeProvider,
  type TaskStatus
} from "@bitagents/shared";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const EMPTY_DB: BitagentsDb = {
  providers: [],
  tasks: []
};

function dataDir(): string {
  if (process.env.BITAGENTS_DATA_DIR) {
    return process.env.BITAGENTS_DATA_DIR;
  }
  // Serverless filesystems (e.g. Vercel) are read-only except for the OS temp
  // dir, so fall back to it there. Data is ephemeral in that case (documented).
  if (process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME) {
    return path.join(os.tmpdir(), "bitagents");
  }
  return path.join(process.cwd(), ".data");
}

function dbPath(): string {
  return path.join(dataDir(), "bitagents.json");
}

export async function readDb(): Promise<BitagentsDb> {
  try {
    const raw = await readFile(dbPath(), "utf8");
    return JSON.parse(raw) as BitagentsDb;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw error;
    }
    return structuredClone(EMPTY_DB);
  }
}

export async function writeDb(db: BitagentsDb): Promise<void> {
  const file = dbPath();
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(db, null, 2)}\n`, "utf8");
}

export async function updateDb<T>(mutator: (db: BitagentsDb) => T | Promise<T>): Promise<T> {
  const db = await readDb();
  const result = await mutator(db);
  await writeDb(db);
  return result;
}

export function recordStatus(task: AgentTask, status: TaskStatus, note?: string): void {
  const at = nowIso();
  task.status = status;
  task.updatedAt = at;
  task.history.push({ status, at, note });
}

export function chooseProvider(db: BitagentsDb): ComputeProvider | undefined {
  const online = db.providers.filter((provider) => provider.status === "online");
  online.sort((a, b) => a.pricePerTaskSol - b.pricePerTaskSol || a.createdAt.localeCompare(b.createdAt));
  return online[0];
}

export function providerPriceOrDefault(provider?: ComputeProvider): number {
  return provider?.pricePerTaskSol ?? DEFAULT_TASK_PRICE_SOL;
}

// Synthetic provider used when no external provider has registered. Keeps the
// task lifecycle (assigned -> computing -> completed) intact for the demo.
export const LOCAL_PROVIDER: ComputeProvider = {
  id: "local-bitagents-provider",
  name: "BITAGENTS Local Compute",
  walletAddress: "LocaLBitAgentsCompute1111111111111111111111",
  computeType: "CPU",
  pricePerTaskSol: DEFAULT_TASK_PRICE_SOL,
  status: "online",
  tasksCompleted: 0,
  reputation: 100,
  createdAt: "1970-01-01T00:00:00.000Z",
  updatedAt: "1970-01-01T00:00:00.000Z"
};

export function findProvider(db: BitagentsDb, id?: string): ComputeProvider | undefined {
  if (!id) return undefined;
  return db.providers.find((provider) => provider.id === id);
}
