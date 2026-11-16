use aomi_sdk::{Secret, dyn_aomi_app};

mod client;
mod tool;

#[derive(Clone, Default)]
pub struct Bitagents;

dyn_aomi_app!(
    app = Bitagents,
    name = "bitagents",
    version = "0.1.0",
    preamble = include_str!("preamble.md"),
    tools = [tool::DiscoverStrategies, tool::GetWallet],
    secrets = [
        Secret::new("BITAGENTS_API_URL", "Operator-configured BITAGENTS API origin (HTTPS).", true),
        Secret::new("BITAGENTS_INTERNAL_API_KEY", "Operator's AGENTS_INTERNAL_API_KEY for the BITAGENTS API.", true),
        Secret::new("BITAGENTS_SESSION_TOKEN", "Your BITAGENTS wallet-session token. Configure through Aomi credentials, never in chat.", true).user_owned(),
    ],
    namespaces = [],
    skills = [{
        id: "bitagents/dca",
        description: "Create, configure and monitor recurring Solana token-buying agents powered by BITAGENTS Python strategies",
        tags: ["trading", "dca", "solana", "strategy"],
        tools: [tool::ListStrategies, tool::GetStrategy, tool::CreateStrategy,
            tool::UpdateStrategy, tool::SetStrategyStatus, tool::RunStrategy, tool::StrategyHistory],
        sections: { instructions: "skill/dca.md" },
    }],
);

#[cfg(test)]
mod tests {
    use super::*;
    use aomi_sdk::DynAomiApp;
    #[test]
    fn dca_tools_are_owned_by_the_strategy_skill() {
        let manifest = Bitagents.manifest();
        assert_eq!(manifest.skills[0].id, "bitagents/dca");
        assert!(
            manifest.skills[0]
                .injected_tools
                .iter()
                .any(|name| name == "run_strategy")
        );
        aomi_sdk::validate_app_skills_with_tools(&manifest.name, &manifest.skills, &manifest.tools)
            .unwrap();
        assert!(
            manifest
                .secrets
                .unwrap()
                .iter()
                .any(|s| s.name == "BITAGENTS_SESSION_TOKEN" && s.user_own)
        );
    }
}
