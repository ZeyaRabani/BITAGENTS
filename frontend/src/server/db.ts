import {
  DEFAULT_TASK_PRICE_SOL,
  nowIso,
  type AgentTask,
  type BitagentsDb,
  type ComputeProvider,
  type TaskStatus
} from "@bitagents/shared";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";

const EMPTY_DB: BitagentsDb = {
  providers: [],
  tasks: []
};

function repoRoot() {
  if (process.env.BITAGENTS_DATA_DIR) {
    return process.env.BITAGENTS_DATA_DIR;
  }

  if (process.cwd().endsWith(path.join("apps", "web"))) {
    return path.resolve(process.cwd(), "../..");
  }

  return process.cwd();
}

function dbPath() {
  const base = process.env.BITAGENTS_DATA_DIR || path.join(repoRoot(), ".data");
  return path.join(base, "bitagents.json");
}

export async function readDb(): Promise<BitagentsDb> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const raw = await readFile(dbPath(), "utf8");
      if (raw.length === 0) {
        throw new SyntaxError("Empty database file");
      }
      return JSON.parse(raw) as BitagentsDb;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") {
        return structuredClone(EMPTY_DB);
      }
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 15));
    }
  }
  throw lastError;
}

export async function writeDb(db: BitagentsDb) {
  const file = dbPath();
  await mkdir(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(tmp, `${JSON.stringify(db, null, 2)}\n`, "utf8");
  await rename(tmp, file);
}

export async function updateDb<T>(mutator: (db: BitagentsDb) => T | Promise<T>): Promise<T> {
  const db = await readDb();
  const result = await mutator(db);
  await writeDb(db);
  return result;
}

export function recordStatus(task: AgentTask, status: TaskStatus, note?: string) {
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

export function providerPriceOrDefault(provider?: ComputeProvider) {
  return provider?.pricePerTaskSol ?? DEFAULT_TASK_PRICE_SOL;
}
