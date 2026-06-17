import { mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";

// Point the JSON store at a throwaway temp dir so tests never touch the dev DB.
process.env.BITAGENTS_DATA_DIR = mkdtempSync(path.join(os.tmpdir(), "bitagents-test-"));
// Ensure no external backend is selected during tests.
delete process.env.UPSTASH_REDIS_REST_URL;
delete process.env.UPSTASH_REDIS_REST_TOKEN;
delete process.env.DATABASE_URL;
