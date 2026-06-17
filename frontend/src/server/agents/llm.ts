import type { ComputeEngine } from "@bitagents/shared";

export interface NarrativeRequest {
  system: string;
  prompt: string;
  fallback: string;
}

export interface NarrativeResult {
  text: string;
  engine: ComputeEngine;
}

const TIMEOUT_MS = 20_000;

function clean(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed && trimmed.length > 0 ? trimmed : undefined;
}

async function withTimeout<T>(run: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await run(controller.signal);
  } finally {
    clearTimeout(timer);
  }
}

async function tryOllama(req: NarrativeRequest): Promise<string | null> {
  const baseUrl = clean(process.env.OLLAMA_BASE_URL);
  if (!baseUrl) return null;
  const model = clean(process.env.OLLAMA_MODEL) ?? "llama3.1";

  return withTimeout(async (signal) => {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        prompt: `${req.system}\n\n${req.prompt}`,
        stream: false,
        options: { temperature: 0.4 }
      }),
      signal
    });
    if (!response.ok) return null;
    const data = (await response.json()) as { response?: string };
    return clean(data.response) ?? null;
  });
}

async function tryOpenAi(req: NarrativeRequest): Promise<string | null> {
  const apiKey = clean(process.env.OPENAI_API_KEY);
  if (!apiKey) return null;
  const model = clean(process.env.OPENAI_MODEL) ?? "gpt-4o-mini";
  const baseUrl = clean(process.env.OPENAI_BASE_URL) ?? "https://api.openai.com/v1";

  return withTimeout(async (signal) => {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        temperature: 0.4,
        messages: [
          { role: "system", content: req.system },
          { role: "user", content: req.prompt }
        ]
      }),
      signal
    });
    if (!response.ok) return null;
    const data = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    return clean(data.choices?.[0]?.message?.content) ?? null;
  });
}

async function tryOpenRouter(req: NarrativeRequest): Promise<string | null> {
  const apiKey = clean(process.env.OPENROUTER_API_KEY);
  if (!apiKey) return null;
  const model = clean(process.env.OPENROUTER_MODEL) ?? "openai/gpt-4o-mini";
  const baseUrl = clean(process.env.OPENROUTER_BASE_URL) ?? "https://openrouter.ai/api/v1";

  return withTimeout(async (signal) => {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        temperature: 0.4,
        messages: [
          { role: "system", content: req.system },
          { role: "user", content: req.prompt }
        ]
      }),
      signal
    });
    if (!response.ok) return null;
    const data = (await response.json()) as {
      choices?: Array<{ message?: { content?: string } }>;
    };
    return clean(data.choices?.[0]?.message?.content) ?? null;
  });
}

async function tryAnthropic(req: NarrativeRequest): Promise<string | null> {
  const apiKey = clean(process.env.ANTHROPIC_API_KEY);
  if (!apiKey) return null;
  const model = clean(process.env.ANTHROPIC_MODEL) ?? "claude-3-5-haiku-latest";

  return withTimeout(async (signal) => {
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01"
      },
      body: JSON.stringify({
        model,
        max_tokens: 700,
        system: req.system,
        messages: [{ role: "user", content: req.prompt }]
      }),
      signal
    });
    if (!response.ok) return null;
    const data = (await response.json()) as { content?: Array<{ text?: string }> };
    return clean(data.content?.[0]?.text) ?? null;
  });
}

/**
 * Generate an AI narrative if a model is configured, otherwise return the
 * deterministic fallback. Order of preference: Ollama (local) -> OpenAI ->
 * Anthropic. Any failure quietly falls through to the next option so the demo
 * never breaks because of a missing or flaky model.
 */
export async function generateNarrative(req: NarrativeRequest): Promise<NarrativeResult> {
  const providers: Array<[ComputeEngine, (r: NarrativeRequest) => Promise<string | null>]> = [
    ["ollama", tryOllama],
    ["openai", tryOpenAi],
    ["anthropic", tryAnthropic]
  ];

  // OpenRouter shares the OpenAI-compatible shape; reported as "openai" engine.
  const all: Array<[ComputeEngine, (r: NarrativeRequest) => Promise<string | null>]> = [
    ["openai", tryOpenRouter],
    ...providers
  ];

  for (const [engine, run] of all) {
    try {
      const text = await run(req);
      if (text) {
        return { text, engine };
      }
    } catch {
      // Ignore and fall through to the next provider / deterministic fallback.
    }
  }

  return { text: req.fallback, engine: "deterministic" };
}

export function llmConfigured(): boolean {
  return Boolean(
    clean(process.env.OPENROUTER_API_KEY) ||
      clean(process.env.OLLAMA_BASE_URL) ||
      clean(process.env.OPENAI_API_KEY) ||
      clean(process.env.ANTHROPIC_API_KEY)
  );
}

function extractJsonObject(text: string): unknown | null {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return null;
  try {
    return JSON.parse(text.slice(start, end + 1));
  } catch {
    return null;
  }
}

/**
 * Ask any configured model to return a JSON object. Returns null when no model
 * is configured or all of them fail, so callers always have a deterministic
 * fallback. Used by the DCA natural-language parser as an optional enhancer.
 */
export async function completeJson(system: string, prompt: string): Promise<unknown | null> {
  if (!llmConfigured()) return null;
  const jsonReq: NarrativeRequest = {
    system: `${system}\nRespond with a single minified JSON object and nothing else.`,
    prompt,
    fallback: ""
  };
  const runners = [tryOpenRouter, tryOpenAi, tryAnthropic, tryOllama];
  for (const run of runners) {
    try {
      const text = await run(jsonReq);
      if (text) {
        const parsed = extractJsonObject(text);
        if (parsed) return parsed;
      }
    } catch {
      // fall through
    }
  }
  return null;
}
