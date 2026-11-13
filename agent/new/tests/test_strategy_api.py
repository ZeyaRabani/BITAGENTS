import copy
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

import dca_agent
import deposit_ledger
from strategy_api import DcaStrategy, create_strategy_router


CONFIG = dict(name="Weekly SOL", input_token="USDC", output_token="SOL", amount_per_buy=25,
              interval="1 day", total_budget=100.5, max_executions=4, slippage_bps=100)


class StrategyApiTests(unittest.TestCase):
    def setUp(self):
        self.plans = {}
        def insert(plan):
            self.plans[plan["id"]] = copy.deepcopy(plan)
        def update(plan_id, values):
            self.plans[plan_id].update(values)
            return copy.deepcopy(self.plans[plan_id])
        def token(symbol):
            return dict(symbol=symbol, mint=symbol + "-mint", decimals=6 if symbol == "USDC" else 9)
        patches = [
            patch.object(dca_agent, "_insert_plan_db", side_effect=insert),
            patch.object(dca_agent, "_find_plan_db", side_effect=lambda p: copy.deepcopy(self.plans.get(p))),
            patch.object(dca_agent, "_update_plan_db", side_effect=update),
            patch.object(dca_agent, "load_all_plans", side_effect=lambda w: [copy.deepcopy(p) for p in self.plans.values() if p["user_wallet"] == w]),
            patch.object(dca_agent, "resolve_token", side_effect=token),
            patch.object(dca_agent, "get_wallet_pubkey", return_value="test-agent-wallet"),
            patch.object(deposit_ledger, "check_plan_budget", return_value={}),
            patch.object(deposit_ledger, "get_user_balances", return_value={"balances": [{"token": "USDC", "available": 1000}]}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        def auth(authorization: str | None = Header(default=None)):
            if authorization not in ("Bearer alice", "Bearer bob"):
                raise HTTPException(401)
            return authorization.split()[1]
        app = FastAPI()
        app.include_router(create_strategy_router(auth, {"dca": DcaStrategy(dca_agent)}))
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer alice"}

    def create(self, config=None):
        return self.client.post("/strategies/dca/plans", json={"configuration": config or CONFIG}, headers=self.headers)

    def test_create_edit_preview_pause_history_uses_real_strategy_logic(self):
        response = self.create()
        self.assertEqual(response.status_code, 200, response.text)
        plan_id = response.json()["plan"]["id"]
        path = f"/strategies/dca/plans/{plan_id}"
        plan = self.plans[plan_id]
        self.assertEqual(plan["user_wallet"], "alice")
        self.assertEqual(plan["status"], "active")
        self.assertGreater(plan["next_execution_at"], plan["created_at"])
        with patch.object(dca_agent, "execute_swap_buy", return_value={"status": "dry_run"}) as quote:
            before = copy.deepcopy(self.plans)
            preview = self.client.post("/strategies/dca/run", json={"plan_id": plan_id}, headers=self.headers)
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(before, self.plans)
            self.assertTrue(quote.call_args.kwargs["dry_run"])
            self.assertEqual(quote.call_args.kwargs["user_wallet"], "alice")
        edited = self.client.patch(path, json={"configuration": {"amount_per_buy": 20}}, headers=self.headers)
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(self.plans[plan_id]["amount_per_buy"], 20)
        for action, status in [("pause", "paused"), ("resume", "active"), ("cancel", "cancelled")]:
            result = self.client.post(path + "/status", json={"action": action}, headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.plans[plan_id]["status"], status)
        self.assertEqual(self.client.post(path + "/status", json={"action": "resume"}, headers=self.headers).status_code, 409)
        self.assertEqual(self.client.get(path + "/executions", headers=self.headers).json()["executions"], [])

    def test_owner_is_never_taken_from_parameters(self):
        self.assertEqual(self.create({**CONFIG, "user_wallet": "bob"}).status_code, 422)
        self.assertEqual(self.plans, {})
        plan_id = self.create().json()["plan"]["id"]
        path = f"/strategies/dca/plans/{plan_id}"
        bob = {"Authorization": "Bearer bob"}
        self.assertEqual(self.client.get("/strategies/dca/plans", headers=bob).json()["count"], 0)
        calls = [("get", path, None), ("get", path + "/executions", None),
                 ("post", path + "/status", {"action": "pause"}),
                 ("patch", path, {"configuration": {"amount_per_buy": 10}}),
                 ("post", "/strategies/dca/run", {"plan_id": plan_id})]
        with patch.object(dca_agent, "execute_swap_buy") as quote:
            for method, url, body in calls:
                kwargs = {"headers": bob}
                if body is not None: kwargs["json"] = body
                self.assertEqual(getattr(self.client, method)(url, **kwargs).status_code, 400)
            quote.assert_not_called()
        self.assertEqual(self.plans[plan_id]["status"], "active")

    def test_invalid_or_unbounded_configuration_never_schedules(self):
        for field, value in [("amount_per_buy", -1), ("amount_per_buy", "NaN"), ("total_budget", "Infinity"),
                             ("max_executions", 0), ("slippage_bps", 5001), ("interval", ""), ("start_immediately", True)]:
            self.assertEqual(self.create({**CONFIG, field: value}).status_code, 422, field)
        no_budget = {k: v for k, v in CONFIG.items() if k != "total_budget"}
        self.assertEqual(self.create(no_budget).status_code, 422)
        self.assertEqual(self.create({**CONFIG, "total_budget": 100}).status_code, 400)  # 0.5% fee matters
        self.assertEqual(self.create({**CONFIG, "interval": "when SOL falls"}).status_code, 400)
        self.assertEqual(self.plans, {})

    def test_no_auth_and_no_forced_live_execution(self):
        self.assertEqual(self.client.get("/strategies").status_code, 401)
        self.assertEqual(self.client.get("/strategies/unknown/plans", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post("/strategies/dca/run", json={"plan_id": "x", "mode": "live"}, headers=self.headers).status_code, 422)

    def test_schema_and_parameter_validation_are_available_to_app(self):
        catalog = self.client.get("/strategies", headers=self.headers).json()["strategies"][0]
        self.assertIn("total_budget", catalog["configuration_schema"]["required"])
        self.assertEqual(catalog["execution"], "bitagents_scheduler")
        plan_id = self.create().json()["plan"]["id"]
        self.assertEqual(self.client.patch(f"/strategies/dca/plans/{plan_id}", json={"configuration": {}}, headers=self.headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()
