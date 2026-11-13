use aomi_sdk::{DynToolCallCtx, resolve_secret_value, resolve_user_secret_value};
use reqwest::{Method, Url, blocking::Client, redirect::Policy};
use serde_json::Value;
use std::{io::Read, time::Duration};

pub(crate) struct StrategyClient {
    http: Client,
    base: Url,
    token: String,
    internal_key: String,
}

impl StrategyClient {
    pub(crate) fn from_context(ctx: &DynToolCallCtx) -> Result<Self, String> {
        let base = resolve_secret_value(
            ctx,
            None,
            "BITAGENTS_API_URL",
            "BITAGENTS API origin is not configured",
        )?;
        let internal_key = resolve_secret_value(
            ctx,
            None,
            "BITAGENTS_INTERNAL_API_KEY",
            "BITAGENTS service key is not configured",
        )?;
        let token = resolve_user_secret_value(
            ctx,
            "BITAGENTS_SESSION_TOKEN",
            "Connect your BITAGENTS account in Aomi credentials",
        )?;
        Self::new(&base, token, internal_key)
    }

    fn new(base: &str, token: String, internal_key: String) -> Result<Self, String> {
        let base = Url::parse(base).map_err(|_| "Invalid BITAGENTS API origin")?;
        if base.scheme() != "https"
            || base.host_str().is_none()
            || !base.username().is_empty()
            || base.password().is_some()
            || base.query().is_some()
            || base.fragment().is_some()
            || base.path() != "/"
        {
            return Err(
                "BITAGENTS_API_URL must be an HTTPS origin without a path or credentials".into(),
            );
        }
        let http = Client::builder()
            .timeout(Duration::from_secs(30))
            .redirect(Policy::none())
            .build()
            .map_err(|_| "Cannot initialize BITAGENTS client")?;
        Ok(Self {
            http,
            base,
            token,
            internal_key,
        })
    }

    pub(crate) fn request(
        &self,
        method: Method,
        path: &str,
        body: Option<Value>,
    ) -> Result<Value, String> {
        let url = self.base.join(path).map_err(|_| "Invalid strategy path")?;
        let mut request = self
            .http
            .request(method, url)
            .bearer_auth(&self.token)
            .header("x-internal-key", &self.internal_key);
        if let Some(body) = body {
            request = request.json(&body);
        }
        let response = request.send().map_err(
            |_| "BITAGENTS request failed. Check current plans before retrying a write.",
        )?;
        let status = response.status();
        if !status.is_success() {
            return Err(match status.as_u16() {
                401 => "Your BITAGENTS session expired; reconnect in Aomi credentials".into(),
                403 => "BITAGENTS denied access; check the service key and account permissions".into(),
                400 | 422 => "BITAGENTS rejected the strategy parameters; check the strategy schema, balance and limits".into(),
                404 => "Strategy or plan not found".into(),
                409 => "This strategy cannot make the requested state transition".into(),
                _ => format!("BITAGENTS returned HTTP {status}; check current state before retrying a write"),
            });
        }
        let mut bytes = Vec::new();
        response
            .take(1_048_577)
            .read_to_end(&mut bytes)
            .map_err(|_| "Cannot read BITAGENTS response")?;
        if bytes.len() > 1_048_576 {
            return Err("BITAGENTS response exceeded the size limit".into());
        }
        let value: Value =
            serde_json::from_slice(&bytes).map_err(|_| "BITAGENTS returned invalid JSON")?;
        if !value.is_object() || value.get("error").is_some() {
            return Err("BITAGENTS operation did not succeed".into());
        }
        Ok(value)
    }
}

pub(crate) fn plan_path(id: &str) -> Result<String, String> {
    if id.is_empty()
        || id.len() > 128
        || !id
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
    {
        return Err("Invalid plan ID; use the ID returned by list_strategies".into());
    }
    Ok(format!("/strategies/dca/plans/{id}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ids_cannot_escape_the_plan_route() {
        for id in ["", "../wallet/withdraw", "a?x=1", "a/b", "https:", "%2f"] {
            assert!(plan_path(id).is_err());
        }
        assert_eq!(
            plan_path("abc-123").unwrap(),
            "/strategies/dca/plans/abc-123"
        );
    }
    #[test]
    fn credentials_only_go_to_an_https_origin() {
        for base in [
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/private",
            "https://example.com?x=1",
        ] {
            assert!(StrategyClient::new(base, "token".into(), "key".into()).is_err());
        }
    }
}
