"""Compile an agent spec into an Aomi app: render the Rust crate, test it, build it.

Output is a real cdylib. When AOMI_APPS_DIR is set the plugin is installed into
that Aomi backend's `local/` directory, which is how a self-hosted backend loads apps.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from . import store
from .spec import AgentSpec

TEMPLATE = Path(__file__).parent / "app_template"
OUT_ROOT = Path(os.environ.get("BUILDER_OUT_DIR", Path(__file__).resolve().parents[3] / ".builder"))
VERSION = "0.1.0"
_BUILD_LOCK = threading.Lock()  # one cargo at a time; they share a target dir


def _rs(text: str) -> str:
    """A Rust string literal."""
    return json.dumps(text, ensure_ascii=False)


def render(agent: dict[str, Any]) -> Path:
    spec = AgentSpec.model_validate(agent["spec"])
    app = agent["app_name"]
    limits, strat = spec.limits, spec.strategy
    preamble = (
        f"{spec.app.brief.strip()}\n\n"
        f"You are the BITAGENTS agent \"{spec.name}\". Strategy: {strat.template}, parameters {json.dumps(strat.params)}. "
        f"Limits: at most ${limits.max_trade_usd:g} per trade and ${limits.max_daily_usd:g} per day, paid in {limits.quote}, "
        f"slippage {limits.slippage_bps} bps. These limits are enforced by the strategy service; you cannot raise them. "
        f"Tools: {app.replace('-', '_')}_status reads signals and holdings; {app.replace('-', '_')}_run decides and returns orders. "
        "Follow the run tool's `next` field. In live mode: stage each order with svm_stage_ix exactly as returned, simulate, then commit. "
        "In paper mode: the orders were already simulated on mainnet, so report the fills and stage nothing. Never build a swap yourself, "
        "never trade a token the run tool did not return, and never state a price or signal you did not get from a tool."
    )
    subs = {
        "APP": app,
        "CRATE": app.replace("-", "_"),
        "TOOL_PREFIX": app.replace("-", "_"),
        "VERSION": VERSION,
        "AGENT_ID": agent["id"],
        "SPEC_SHA": agent["spec_sha"],
        "API_URL": os.environ.get("BUILDER_PUBLIC_API_URL", "http://127.0.0.1:8765"),
        "PLATFORM": os.environ.get("AOMI_PLATFORM", "bitagents"),
        "DISPLAY_NAME_JSON": json.dumps(spec.name),
        "PREAMBLE_RS": _rs(preamble),
        "SKILL_DESC_RS": _rs(spec.description),
        "SKILL_MD": spec.app.skill.strip(),
    }
    out = OUT_ROOT / "apps" / app
    if out.exists():
        shutil.rmtree(out)
    for src in TEMPLATE.rglob("*"):
        if src.is_dir():
            continue
        text = src.read_text()
        for k, v in subs.items():
            text = text.replace("{{" + k + "}}", v)
        if "{{" in text and "}}" in text.split("{{", 1)[1][:40]:
            raise RuntimeError(f"unfilled placeholder in {src.name}")
        dst = out / src.relative_to(TEMPLATE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text)
    (out / "spec.json").write_text(json.dumps(agent["spec"], indent=2) + "\n")
    return out


def _cargo(args: list[str], cwd: Path, log: list[dict]) -> None:
    env = {**os.environ, "CARGO_TARGET_DIR": str(OUT_ROOT / "target"), "CARGO_TERM_COLOR": "never"}
    started = time.time()
    proc = subprocess.run(["cargo", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=1800)
    log.append({"step": "cargo " + " ".join(args), "seconds": round(time.time() - started, 1),
                "exit_code": proc.returncode, "tail": (proc.stdout + proc.stderr)[-2500:]})
    if proc.returncode != 0:
        raise RuntimeError(f"cargo {args[0]} failed")


def compile_agent(agent_id: str) -> None:
    """Render, test, build, install. Writes progress to built_agents.build as it goes."""
    agent = store.get_agent(agent_id)
    build: dict[str, Any] = {"spec_sha": agent["spec_sha"], "steps": [], "started_at": time.time()}

    def progress(stage: str) -> None:
        build["stage"] = stage
        store.set_build(agent_id, "building", build)

    hosted_app = os.environ.get("AOMI_HOSTED_APP", "").strip()
    if hosted_app:
        # Hosted Aomi runs one shared app for every agent; deploying is publishing the spec to it.
        try:
            progress("validate")
            AgentSpec.model_validate(agent["spec"])
            progress("publish")
            build["hosted"] = {"app": hosted_app,
                               "note": "Runs on the shared Aomi app, which reads this strategy's spec by id on every call."}
            build["finished_at"] = time.time()
            build["stage"] = "done"
            store.set_build(agent_id, "ready", build)
        except Exception as exc:
            build["error"] = str(exc)
            build["finished_at"] = time.time()
            store.set_build(agent_id, "failed", build)
        return

    try:
        with _BUILD_LOCK:
            progress("render")
            crate = render(agent)
            build["crate_dir"] = str(crate)
            build["files"] = sorted(str(p.relative_to(crate)) for p in crate.rglob("*") if p.is_file())
            progress("test")
            _cargo(["test", "--release"], crate, build["steps"])
            progress("build")
            _cargo(["build", "--release", "--lib"], crate, build["steps"])
            so = OUT_ROOT / "target" / "release" / f"lib{agent['app_name'].replace('-', '_')}.so"
            if not so.exists():
                raise RuntimeError(f"cargo succeeded but {so.name} is missing")
            build["artifact"] = {"path": str(so), "bytes": so.stat().st_size,
                                 "sha256": hashlib.sha256(so.read_bytes()).hexdigest()}
            progress("install")
            apps_dir = os.environ.get("AOMI_APPS_DIR")
            if apps_dir:
                dest = Path(apps_dir) / "local" / so.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".tmp")
                shutil.copy2(so, tmp)
                tmp.replace(dest)
                build["installed"] = {"path": str(dest), "target": "local Aomi backend (AOMI_APPS_DIR)"}
                # The backend scans its plugin directory on a timer. Ready means it has registered the app.
                progress("register")
                from . import aomi_bridge
                waited = time.time()
                while aomi_bridge.configured() is None and aomi_bridge.application_id(agent["app_name"]) is None:
                    if time.time() - waited > 90:
                        raise RuntimeError("the Aomi backend did not register the app within 90 seconds")
                    time.sleep(2)
                build["registered_seconds"] = round(time.time() - waited, 1)
            else:
                build["installed"] = None
                build["install_note"] = "AOMI_APPS_DIR is not set, so the plugin was built but not loaded into an Aomi backend."
        build["finished_at"] = time.time()
        build["stage"] = "done"
        store.set_build(agent_id, "ready", build)
    except Exception as exc:  # recorded for the owner; the build log has the detail
        build["error"] = str(exc)
        build["finished_at"] = time.time()
        store.set_build(agent_id, "failed", build)


def start(agent_id: str) -> None:
    store.set_build(agent_id, "building", {"stage": "queued", "steps": []})
    threading.Thread(target=compile_agent, args=(agent_id,), daemon=True, name=f"build-{agent_id}").start()
