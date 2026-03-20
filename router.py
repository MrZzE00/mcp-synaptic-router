#!/usr/bin/env python3
"""
Synaptic Router — Router Hybride 4-TIER
Route les prompts vers le modèle optimal (local via Ollama ou cloud via Anthropic).

Usage: python router.py "votre prompt" [--category security] [--verbose]
"""

import argparse
import json
import logging
import operator
import os
import pathlib
import sys
import time
from urllib.parse import urlparse

import httpx
import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("SYNAPTIC_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("synaptic-router")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_DIR = pathlib.Path(__file__).parent.resolve()
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.yaml"

MAX_PROMPT_LENGTH = 100_000  # ~25K tokens
VALID_CATEGORIES = {"security", "architecture", "general"}
VALID_BACKENDS = {"ollama", "anthropic"}

ALLOWED_OLLAMA_HOSTS = {"localhost", "127.0.0.1", "::1"}
ALLOWED_SCHEMES = {"http", "https"}

REQUIRED_CONFIG_KEYS = {"tiers", "routing", "ollama", "anthropic"}
REQUIRED_TIER_KEYS = {"name", "model", "backend"}

# ---------------------------------------------------------------------------
# Safe condition evaluation (replaces eval())
# ---------------------------------------------------------------------------
OPERATORS = {
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}


def evaluate_condition(condition: dict, ctx: dict) -> bool:
    """Evaluate a declarative condition safely — no eval(), no exec().

    Supported formats:
      - Simple:  {"field": "category", "op": "in", "value": ["security"]}
      - AND:     {"all": [<condition>, ...]}
      - OR:      {"any": [<condition>, ...]}
      - Always:  {"always": true}
    """
    if not isinstance(condition, dict):
        raise ValueError(f"Condition must be a dict, got {type(condition).__name__}")

    # Always-true shortcut
    if "always" in condition:
        return bool(condition["always"])

    # Compound AND
    if "all" in condition:
        return all(evaluate_condition(sub, ctx) for sub in condition["all"])

    # Compound OR
    if "any" in condition:
        return any(evaluate_condition(sub, ctx) for sub in condition["any"])

    # Simple field/op/value
    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")

    if field is None or op is None or value is None:
        raise ValueError(f"Condition must have 'field', 'op', 'value': {condition}")

    if op not in OPERATORS:
        raise ValueError(f"Unsupported operator: {op}. Allowed: {list(OPERATORS)}")

    if field not in ctx:
        logger.warning("Unknown field '%s' in condition — evaluates to False", field)
        return False

    return OPERATORS[op](ctx[field], value)


# ---------------------------------------------------------------------------
# Configuration loading & validation
# ---------------------------------------------------------------------------
def validate_config(config: dict) -> dict:
    """Validate config schema. Raises ValueError on invalid config."""
    missing = REQUIRED_CONFIG_KEYS - set(config.keys())
    if missing:
        raise ValueError(f"Missing config keys: {missing}")

    if not isinstance(config.get("tiers"), dict):
        raise ValueError("'tiers' must be a mapping")

    for tier_key, tier in config["tiers"].items():
        tier_missing = REQUIRED_TIER_KEYS - set(tier.keys())
        if tier_missing:
            raise ValueError(f"Missing keys in {tier_key}: {tier_missing}")
        if tier["backend"] not in VALID_BACKENDS:
            raise ValueError(
                f"Invalid backend '{tier['backend']}' in {tier_key}. "
                f"Allowed: {VALID_BACKENDS}"
            )

    rules = config.get("routing", {}).get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("'routing.rules' must be a list")

    return config


def load_config(config_path: str | pathlib.Path | None = None) -> dict:
    """Load and validate config. Restricts path to project directory."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    else:
        config_path = pathlib.Path(config_path).resolve()
        if not str(config_path).startswith(str(PROJECT_DIR)):
            raise ValueError(
                f"Config path must be inside {PROJECT_DIR}, got {config_path}"
            )

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return validate_config(config)


# ---------------------------------------------------------------------------
# Token estimation & category classification
# ---------------------------------------------------------------------------
def estimate_tokens(text: str) -> int:
    """Quick estimation: ~4 chars per token."""
    return max(1, len(text) // 4)


def classify_category(prompt: str) -> str:
    """Keyword-based category classification."""
    prompt_lower = prompt.lower()
    security_kw = [
        "sécurit", "security", "vulnérab", "vulnerability",
        "auth", "permission", "sql injection", "xss", "csrf",
    ]
    arch_kw = [
        "architecture", "design pattern", "api design",
        "schema", "microservice", "modèle de données",
    ]
    if any(kw in prompt_lower for kw in security_kw):
        return "security"
    if any(kw in prompt_lower for kw in arch_kw):
        return "architecture"
    return "general"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def validate_prompt(prompt: str) -> str:
    """Validate prompt length and content."""
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty.")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(
            f"Prompt too long ({len(prompt)} chars, max {MAX_PROMPT_LENGTH})."
        )
    return prompt.strip()


def validate_category(category: str | None) -> str | None:
    """Validate category against whitelist."""
    if category is not None and category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category: '{category}'. Valid: {VALID_CATEGORIES}"
        )
    return category


# ---------------------------------------------------------------------------
# Tier selection (safe, fail-closed)
# ---------------------------------------------------------------------------
def select_tier(
    prompt: str,
    category: str,
    token_count: int,
    latency_critical: bool,
    config: dict,
) -> tuple:
    """Apply routing rules and return (tier_config, tier_key).

    Fail-closed: on any rule evaluation error, routes to tier3 (most secure).
    """
    tiers = config["tiers"]
    rules = config["routing"]["rules"]

    ctx = {
        "category": category,
        "token_count": token_count,
        "latency_critical": latency_critical,
        "confidence": 0.8,
        "complexity": "standard",
        "tier1_available": tiers.get("tier1", {}).get("available", False),
    }

    for rule in rules:
        condition = rule.get("condition", {})
        rule_name = rule.get("name", "unknown")
        try:
            result = evaluate_condition(condition, ctx)
        except Exception as e:
            logger.error(
                "Rule '%s' evaluation failed: %s — fail-closed to tier3",
                rule_name,
                e,
            )
            if "tier3" in tiers:
                return tiers["tier3"], "tier3"
            raise RuntimeError(f"Rule evaluation failed and tier3 unavailable: {e}")
        if result:
            tier_key = rule["tier"]
            if tier_key not in tiers:
                logger.error("Rule '%s' references unknown tier '%s'", rule_name, tier_key)
                continue
            logger.info(
                "Routed via rule '%s' → %s (%s)",
                rule_name,
                tier_key,
                tiers[tier_key]["name"],
            )
            return tiers[tier_key], tier_key

    # Default fallback
    logger.info("No rule matched — default to tier2")
    return tiers["tier2"], "tier2"


# ---------------------------------------------------------------------------
# SSRF protection
# ---------------------------------------------------------------------------
def validate_ollama_host(host: str) -> str:
    """Validate Ollama host against allowlist to prevent SSRF."""
    parsed = urlparse(host)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Disallowed scheme: {parsed.scheme}")
    hostname = parsed.hostname
    if hostname not in ALLOWED_OLLAMA_HOSTS:
        if os.environ.get("SYNAPTIC_ALLOW_REMOTE_OLLAMA") == "1":
            logger.warning("Remote Ollama host allowed via env override: %s", hostname)
            return host
        raise ValueError(
            f"Ollama host '{hostname}' not in allowlist {ALLOWED_OLLAMA_HOSTS}. "
            f"Set SYNAPTIC_ALLOW_REMOTE_OLLAMA=1 to override."
        )
    return host


# ---------------------------------------------------------------------------
# Backend calls
# ---------------------------------------------------------------------------
def call_ollama(prompt: str, model: str, host: str, timeout: int) -> str:
    """Call Ollama API with SSRF-validated host."""
    host = validate_ollama_host(host)
    url = f"{host}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["response"]


def call_anthropic(prompt: str, model: str, timeout: int) -> str:
    """Call Anthropic API (Claude). Requires ANTHROPIC_API_KEY env var."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. "
            "This env var is required for tier3 (Claude) routing."
        )
    import anthropic

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def route_and_call(
    prompt: str,
    category: str | None = None,
    latency_critical: bool = False,
    verbose: bool = False,
    config_path: str | None = None,
) -> dict:
    """Route a prompt to the optimal model and return the response."""
    prompt = validate_prompt(prompt)
    category = validate_category(category)

    config = load_config(config_path)
    token_count = estimate_tokens(prompt)

    if category is None:
        category = classify_category(prompt)

    tier_config, tier_key = select_tier(
        prompt, category, token_count, latency_critical, config
    )

    if verbose:
        print(f"[Synaptic] Tier: {tier_key} ({tier_config['name']})", file=sys.stderr)
        print(f"[Synaptic] Model: {tier_config['model']}", file=sys.stderr)
        print(f"[Synaptic] Tokens: {token_count}", file=sys.stderr)
        print(f"[Synaptic] Category: {category}", file=sys.stderr)

    start = time.time()

    backend = tier_config["backend"]
    if backend == "ollama":
        ollama_cfg = config["ollama"]
        response = call_ollama(
            prompt,
            tier_config["model"],
            ollama_cfg["host"],
            ollama_cfg["timeout_seconds"],
        )
    elif backend == "anthropic":
        anthropic_cfg = config["anthropic"]
        response = call_anthropic(
            prompt, tier_config["model"], anthropic_cfg["timeout_seconds"]
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")

    latency_ms = int((time.time() - start) * 1000)

    logger.info(
        "Response from %s/%s in %dms (category=%s, tokens=%d)",
        tier_key,
        tier_config["model"],
        latency_ms,
        category,
        token_count,
    )

    return {
        "tier": tier_key,
        "model": tier_config["model"],
        "backend": backend,
        "category": category,
        "tokens_estimated": token_count,
        "latency_ms": latency_ms,
        "response": response,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Synaptic Router — Hybrid 4-Tier LLM Router"
    )
    parser.add_argument("prompt", help="The prompt to route")
    parser.add_argument(
        "--category",
        choices=list(VALID_CATEGORIES),
        help="Force category (security, architecture, general)",
    )
    parser.add_argument(
        "--latency-critical",
        action="store_true",
        help="Prioritize latency (activates BitNet if available)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show routing details")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Full JSON output",
    )
    parser.add_argument("--config", help="Path to alternative config.yaml")
    args = parser.parse_args()

    result = route_and_call(
        prompt=args.prompt,
        category=args.category,
        latency_critical=args.latency_critical,
        verbose=args.verbose,
        config_path=args.config,
    )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["response"])


if __name__ == "__main__":
    main()
