use std::time::Duration;

use aomi_sdk::{DynAomiTool, DynToolCallCtx, resolve_secret_value};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};

use crate::{AGENT_ID, Agent, DEFAULT_API_URL, SPEC_SHA};

fn api(ctx: &DynToolCallCtx, path: &str, body: Value) -> Result<Value, String> {
    let base = resolve_secret_value(ctx, None, "BITAGENTS_API_URL", "")
        .unwrap_or_else(|_| DEFAULT_API_URL.to_string());
    let key = resolve_secret_value(
        ctx,
        None,
        "BITAGENTS_APP_KEY",
        "BITAGENTS_APP_KEY is not configured for this app",
    )?;
    let url = format!("{}/builder/agents/{AGENT_ID}/{path}", base.trim_end_matches('/'));
    let resp = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(90))
        .build()
        .map_err(|e| format!("http client: {e}"))?
        .post(&url)
        .header("x-app-key", key)
        .json(&body)
        .send()
        .map_err(|e| format!("BITAGENTS strategy service unreachable: {e}"))?;
    let status = resp.status();
    let value: Value = resp.json().map_err(|e| format!("bad response from strategy service: {e}"))?;
    if !status.is_success() {
        let detail = value.get("detail").and_then(Value::as_str).unwrap_or("request failed");
        return Err(format!("strategy service returned {status}: {detail}"));
    }
    Ok(value)
}

fn wallet(ctx: &DynToolCallCtx) -> Result<String, String> {
    ctx.attribute_string(&["domain", "svm", "address"])
        .filter(|a| !a.trim().is_empty())
        .ok_or_else(|| "no Solana wallet is connected to this session".to_string())
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct StatusArgs {}

pub struct Status;

impl DynAomiTool for Status {
    type App = Agent;
    type Args = StatusArgs;

    const NAME: &'static str = "{{TOOL_PREFIX}}_status";
    const DESCRIPTION: &'static str = "Show this agent's strategy, limits, the wallet's holdings and the latest signals. Read-only: never trades.";

    fn run(_app: &Agent, _args: StatusArgs, ctx: DynToolCallCtx) -> Result<Value, String> {
        let wallet = wallet(&ctx)?;
        let mut out = api(&ctx, "evaluate", json!({ "wallet": wallet, "build": false }))?;
        out["spec_sha"] = json!(SPEC_SHA);
        Ok(out)
    }
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct RunArgs {}

pub struct Run;

impl DynAomiTool for Run {
    type App = Agent;
    type Args = RunArgs;

    const NAME: &'static str = "{{TOOL_PREFIX}}_run";
    const DESCRIPTION: &'static str = "Run the strategy once for the connected wallet. Returns the decision and a `next` field saying what to do. A live agent returns exact unsigned swap instructions to stage with svm_stage_ix; a paper agent returns fills already simulated on mainnet. Does not sign or send anything itself.";

    fn run(_app: &Agent, _args: RunArgs, ctx: DynToolCallCtx) -> Result<Value, String> {
        let wallet = wallet(&ctx)?;
        let mut out = api(&ctx, "evaluate", json!({ "wallet": wallet, "build": true }))?;
        // The strategy service says what happens next: stage for signing (live) or report simulated fills (paper).
        if out.get("next").is_none() {
            out["next"] = json!("Report the signals and notes to the user. Do not stage anything.");
        }
        Ok(out)
    }
}
