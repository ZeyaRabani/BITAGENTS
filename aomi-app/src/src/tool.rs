use crate::{
    Bitagents,
    client::{StrategyClient, plan_path},
};
use aomi_sdk::{DynAomiTool, DynToolCallCtx};
use reqwest::Method;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Empty {}

#[derive(Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    /// Exact ID returned by create_strategy or list_strategies.
    plan_id: String,
}

#[derive(Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Configuration {
    name: String,
    /// Token symbol or Solana mint. Amounts are in units of this token.
    input_token: String,
    output_token: String,
    amount_per_buy: f64,
    /// For example "1 hour" or "1 day".
    interval: String,
    /// Maximum cumulative spend including BITAGENTS' platform fee.
    total_budget: f64,
    max_executions: u32,
    /// Basis points: 100 is 1 percent.
    slippage_bps: u32,
}

#[derive(Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Changes {
    #[serde(skip_serializing_if = "Option::is_none")]
    amount_per_buy: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    interval: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    total_budget: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_executions: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    slippage_bps: Option<u32>,
}

#[derive(Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Update {
    plan_id: String,
    configuration: Changes,
}

#[derive(Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Pause,
    Resume,
    Cancel,
}

#[derive(Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Status {
    plan_id: String,
    action: Action,
}

// Every tool uses the same authenticated transport. Arguments remain typed;
// models cannot choose URLs, owners, session tokens or arbitrary service calls.
macro_rules! tool {
    ($ty:ident, $args:ty, $name:literal, $description:literal, |$client:ident, $input:ident| $body:block) => {
        pub struct $ty;
        impl DynAomiTool for $ty {
            type App = Bitagents;
            type Args = $args;
            const NAME: &'static str = $name;
            const DESCRIPTION: &'static str = $description;
            fn run(
                _: &Bitagents,
                $input: Self::Args,
                ctx: DynToolCallCtx,
            ) -> Result<Value, String> {
                let $client = StrategyClient::from_context(&ctx)?;
                $body
            }
        }
    };
}

tool!(
    DiscoverStrategies,
    Empty,
    "discover_strategies",
    "Discover available BITAGENTS strategy skills, their parameter schemas and supported execution modes.",
    |client, _args| { client.request(Method::GET, "/strategies", None) }
);
tool!(
    GetWallet,
    Empty,
    "get_strategy_wallet",
    "Get or provision the authenticated user's BITAGENTS deposit wallet before configuring a strategy. Does not transfer funds.",
    |client, _args| {
        let wallet = client.request(Method::GET, "/wallet/agent", None)?;
        // Do not expose the upstream RPC URL or operator diagnostics.
        Ok(json!({
            "agent_wallet": wallet["agent_wallet"],
            "configured": wallet["configured"],
            "wallet_provider": wallet["wallet_provider"],
            "per_user_wallet": wallet["per_user_wallet"],
            "cluster": wallet["cluster"],
            "allowed_deposit_tokens": wallet["allowed_deposit_tokens"],
        }))
    }
);
tool!(
    ListStrategies,
    Empty,
    "list_strategies",
    "List this user's persisted DCA agents and their schedules.",
    |client, _args| { client.request(Method::GET, "/strategies/dca/plans", None) }
);
tool!(
    GetStrategy,
    Plan,
    "get_strategy",
    "Read one DCA agent's configuration, remaining budget and schedule.",
    |client, args| { client.request(Method::GET, &plan_path(&args.plan_id)?, None) }
);
tool!(
    CreateStrategy,
    Configuration,
    "create_strategy",
    "Create and activate a bounded recurring DCA agent after the user approves all parameters. Authorizes future spending; first execution is after the interval. Never retry an uncertain creation without checking existing plans.",
    |client, args| {
        client.request(
            Method::POST,
            "/strategies/dca/plans",
            Some(json!({"configuration": args})),
        )
    }
);
tool!(
    UpdateStrategy,
    Update,
    "update_strategy",
    "Change the amount, interval, budget, execution cap or slippage of an existing DCA agent. Obtain approval before increasing spending.",
    |client, args| {
        client.request(
            Method::PATCH,
            &plan_path(&args.plan_id)?,
            Some(json!({"configuration": args.configuration})),
        )
    }
);
tool!(
    SetStrategyStatus,
    Status,
    "set_strategy_status",
    "Pause, resume or cancel a DCA agent's future scheduled runs. Resume can authorize an immediate overdue buy; already in-flight trades cannot be retracted.",
    |client, args| {
        client.request(
            Method::POST,
            &format!("{}/status", plan_path(&args.plan_id)?),
            Some(json!({"action": args.action})),
        )
    }
);
tool!(
    RunStrategy,
    Plan,
    "run_strategy",
    "Run the DCA skill in preview mode: obtain a quote for the user's saved strategy without signing, sending or modifying the schedule. Scheduled live execution belongs to BITAGENTS.",
    |client, args| {
        plan_path(&args.plan_id)?;
        client.request(
            Method::POST,
            "/strategies/dca/run",
            Some(json!({"plan_id": args.plan_id, "mode": "preview"})),
        )
    }
);
tool!(
    StrategyHistory,
    Plan,
    "strategy_history",
    "Read a DCA agent's execution history, errors and confirmed transaction signatures.",
    |client, args| {
        client.request(
            Method::GET,
            &format!("{}/executions", plan_path(&args.plan_id)?),
            None,
        )
    }
);
