type Plan = {
  id: string;
  name: string;
  status: string;
  input_token: string;
  output_token: string;
  amount_per_buy: number;
  interval: string;
  total_budget: number;
  max_executions: number;
  executions_count: number;
  spent_so_far: number;
  next_execution_at: string;
  slippage_bps: number;
};
const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const input = (id: string) => $<HTMLInputElement>(id);
let plan: Plan | undefined;
let editing = false;
const money = (n: number) =>
  n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
function text(id: string, value: string) {
  $(id).textContent = value;
}
function show(id: string, visible: boolean) {
  $(id).classList.toggle("hidden", !visible);
}
function message(content: string, user = false) {
  const node = document.createElement("div");
  node.className = `bubble${user ? " user" : ""}`;
  node.textContent = content;
  $("chat").append(node);
}
function log(line: string) {
  const node = document.createElement("div");
  node.textContent = line;
  $("event-log").prepend(node);
  while ($("event-log").children.length > 7)
    $("event-log").lastElementChild?.remove();
}
async function api(path: string, method = "GET", body?: unknown) {
  const response = await fetch(path, {
    method,
    headers: {
      Authorization: "Bearer local-preview",
      "Content-Type": "application/json",
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  log(`${response.status} ${method} ${path}`);
  if (!response.ok) {
    const detail =
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail);
    throw new Error(detail || "The operation failed");
  }
  if (result.error) throw new Error(result.error);
  return result;
}
async function action(button: HTMLButtonElement, fn: () => Promise<void>) {
  button.disabled = true;
  try {
    await fn();
  } catch (e) {
    message(e instanceof Error ? e.message : "Request failed");
  } finally {
    button.disabled = false;
  }
}
function config() {
  return {
    name: input("name").value,
    input_token: "USDC",
    output_token: "SOL",
    amount_per_buy: Number(input("amount").value),
    interval: input("interval").value,
    total_budget: Number(input("budget").value),
    max_executions: Number(input("count").value),
    slippage_bps: Number(input("slippage").value),
  };
}
function recalc() {
  input("budget").value = (
    Number(input("amount").value) *
    Number(input("count").value) *
    1.005
  ).toFixed(2);
}
input("amount").addEventListener("input", recalc);
input("count").addEventListener("input", recalc);
$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const prompt = input("prompt").value.trim();
  if (!prompt) return;
  message(prompt, true);
  const match =
    /^buy\s+(\d+(?:\.\d+)?)\s+USDC\s+of\s+SOL\s+daily\s+for\s+(\d+)\s+buys\.?$/i.exec(
      prompt,
    );
  if (!match) {
    message(
      "This guided preview supports recurring SOL buys, not arbitrary strategies. Try “Buy 25 USDC of SOL daily for 4 buys”. Live Aomi will interpret the request through the skill’s typed tools.",
    );
    return;
  }
  input("amount").value = match[1];
  input("count").value = match[2];
  recalc();
  editing = false;
  message(
    "I’ve prepared a recurring SOL strategy. Review the limits below. It will start after one interval and stop at the budget or execution cap.",
  );
  show("review", true);
  show("composer", false);
  $("review").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("discard").onclick = () => {
  show("review", false);
  show("composer", !plan);
  editing = false;
};
$("authorize").onclick = () =>
  action($<HTMLButtonElement>("authorize"), async () => {
    const configuration = config();
    if (editing && plan) {
      const { name, input_token, output_token, ...changes } = configuration;
      await api(`/strategies/dca/plans/${plan.id}`, "PATCH", {
        configuration: changes,
      });
      message(
        "Your limits are updated. Future runs use the saved configuration.",
      );
    } else {
      const response = await api("/strategies/dca/plans", "POST", {
        configuration,
      });
      plan = response.plan;
      message(
        "Your agent is active. BITAGENTS will run it on schedule, even after this chat closes. You can preview the next buy or pause future runs here.",
      );
    }
    show("review", false);
    editing = false;
    await refresh();
    $("agent").scrollIntoView({ behavior: "smooth", block: "start" });
  });
function row(label: string, value: string) {
  const element = document.createElement("div");
  element.className = "metrics";
  const a = document.createElement("span");
  a.textContent = label;
  const b = document.createElement("strong");
  b.textContent = value;
  element.append(a, b);
  return element;
}
async function refresh() {
  if (!plan) return;
  plan = (await api(`/strategies/dca/plans/${plan.id}`)) as Plan;
  show("agent", true);
  text("agent-name", plan.name);
  text("agent-id", `BITAGENTS / DCA · ${plan.id}`);
  text("status", plan.status);
  $("status").classList.toggle("paused", plan.status === "paused");
  text("pause", plan.status === "paused" ? "Resume agent" : "Pause agent");
  $<HTMLButtonElement>("tick").disabled = plan.status !== "active";
  $("details").replaceChildren(
    row("Each buy", `${money(plan.amount_per_buy)} USDC → SOL`),
    row("Schedule", `Every ${plan.interval}`),
    row(
      "Budget used",
      `${money(plan.spent_so_far)} / ${money(plan.total_budget)} USDC`,
    ),
    row("Runs completed", `${plan.executions_count} / ${plan.max_executions}`),
    row(
      "Next run",
      plan.status === "active"
        ? new Date(plan.next_execution_at).toLocaleString("en-GB", {
            timeZone: "UTC",
          }) + " UTC"
        : "Paused",
    ),
  );
  const history = await api(`/strategies/dca/plans/${plan.id}/executions`);
  $("history").replaceChildren();
  for (const run of (history.executions || []).slice().reverse()) {
    const node = document.createElement("div");
    node.className = "receipt";
    const title = document.createElement("div");
    title.textContent = `${run.result.status === "success" ? "Fixture run completed" : "Run failed"} · ${money(run.amount)} USDC`;
    const note = document.createElement("small");
    note.textContent = `${run.result.receipt || "No on-chain receipt"} · fee ${money(run.platform_fee)} USDC`;
    node.append(title, note);
    $("history").append(node);
  }
}
$("preview").onclick = () =>
  action($<HTMLButtonElement>("preview"), async () => {
    if (!plan) return;
    const result = await api("/strategies/dca/run", "POST", {
      plan_id: plan.id,
      mode: "preview",
    });
    text(
      "run-result",
      `Quote preview: ${money(result.input_amount)} USDC ≈ ${result.estimated_output} SOL. ${result.price_source}. No trade submitted.`,
    );
  });
$("pause").onclick = () =>
  action($<HTMLButtonElement>("pause"), async () => {
    if (!plan) return;
    const next = plan.status === "paused" ? "resume" : "pause";
    if (next === "resume") {
      message(
        "Resuming authorizes the saved schedule; an overdue run may execute on the next tick.",
        true,
      );
    }
    await api(`/strategies/dca/plans/${plan.id}/status`, "POST", {
      action: next,
    });
    await refresh();
    message(
      next === "pause"
        ? "Agent paused. Future scheduled buys are stopped. Existing history and limits are preserved."
        : "Agent resumed with its saved limits.",
    );
  });
$("tick").onclick = () =>
  action($<HTMLButtonElement>("tick"), async () => {
    if (!plan) return;
    await api(`/demo/tick/${plan.id}`, "POST");
    await refresh();
  });
$("edit").onclick = () => {
  if (!plan) return;
  editing = true;
  input("name").value = plan.name;
  input("name").disabled = true;
  input("amount").value = String(plan.amount_per_buy);
  input("count").value = String(plan.max_executions);
  input("budget").value = String(plan.total_budget);
  input("interval").value = plan.interval;
  input("slippage").value = String(plan.slippage_bps);
  text("authorize", "Save & authorize changes");
  show("review", true);
  $("review").scrollIntoView({ behavior: "smooth", block: "center" });
};
async function boot() {
  try {
    const result = await api("/strategies");
    text(
      "event-log",
      `${result.strategies.length} strategy skill available · DCA. API connected · fixture execution only`,
    );
  } catch (e) {
    message(String(e));
  }
}
void boot();
