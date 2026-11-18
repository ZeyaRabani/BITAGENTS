"""Agent Builder: turn a plain-language brief into a deployed Aomi app.

input  -> spec.compose_spec   one LLM pass, validated against the strategy's schema
compile -> compiler.compile   renders a Rust Aomi app crate and runs cargo
run    -> contract.Strategy   Python decides, returns unsigned Jupiter instructions
"""
