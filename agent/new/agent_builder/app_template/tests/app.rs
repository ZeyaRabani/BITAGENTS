use aomi_sdk::testing::{TestCtxBuilder, run_tool};
use aomi_sdk::{DynAomiApp, DynAomiTool, validate_app_skills_with_tools};
use {{CRATE}}::{Agent, Run, Status};
use serde_json::json;

#[test]
fn skills_and_tools_are_valid() {
    let manifest = Agent.manifest();
    validate_app_skills_with_tools(&manifest.name, &manifest.skills, &manifest.tools)
        .expect("app manifest is valid");
}

#[test]
fn run_needs_a_connected_solana_wallet() {
    let ctx = TestCtxBuilder::new(Run::NAME).build();
    let err = run_tool::<Run>(&Agent, json!({}), ctx).err().unwrap();
    assert!(err.contains("no Solana wallet"), "{err}");
}

#[test]
fn status_needs_the_app_key() {
    let ctx = TestCtxBuilder::new(Status::NAME)
        .attribute("domain", json!({ "svm": { "address": "11111111111111111111111111111112" } }))
        .build();
    let err = run_tool::<Status>(&Agent, json!({}), ctx).err().unwrap();
    assert!(err.contains("BITAGENTS_APP_KEY"), "{err}");
}
