#!/usr/bin/env python3
"""
Synaptic Router — MCP Server
Exposes the hybrid 4-tier router as MCP tools for Claude Code.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP

from router import (
    classify_category,
    estimate_tokens,
    load_config,
    select_tier,
    validate_category,
    validate_prompt,
)

logger = logging.getLogger("synaptic-router.mcp")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

mcp = FastMCP("synaptic-router")


@mcp.tool()
async def query_local_model(
    prompt: str,
    category: str = None,
    latency_critical: bool = False,
) -> str:
    """
    Route the prompt to the optimal local model (GLM-4 or Qwen) and return the response.
    Security and architecture categories are automatically redirected to Claude (tier3).

    Parameters:
      - prompt: Text to send to the model
      - category: "security"|"architecture"|"general" (None = auto-detected by keywords)
      - latency_critical: True to favor BitNet if available
    """
    from router import route_and_call

    try:
        prompt = validate_prompt(prompt)
        category = validate_category(category)
    except ValueError as e:
        return f"Validation error: {e}"

    result = await asyncio.to_thread(
        route_and_call, prompt, category, latency_critical, False
    )
    return (
        f"[{result['tier']} / {result['model']} / {result['latency_ms']}ms]\n\n"
        f"{result['response']}"
    )


@mcp.tool()
async def explain_routing(
    prompt: str,
    category: str = None,
) -> str:
    """
    Explain the routing decision for a prompt without calling the model.
    Useful to understand why a prompt goes to GLM-4 vs Qwen vs Claude.
    """
    try:
        prompt = validate_prompt(prompt)
        category = validate_category(category)
    except ValueError as e:
        return f"Validation error: {e}"

    config = load_config(CONFIG_PATH)
    token_count = estimate_tokens(prompt)
    detected_category = category or classify_category(prompt)
    tier_config, tier_key = select_tier(
        prompt, detected_category, token_count, False, config
    )
    return (
        f"Routing: {tier_key} ({tier_config['name']})\n"
        f"Model: {tier_config['model']}\n"
        f"Category: {detected_category}\n"
        f"Estimated tokens: {token_count}"
    )


@mcp.tool()
async def list_available_models() -> str:
    """Return available models per tier with their current status."""
    config = load_config(CONFIG_PATH)
    lines = []
    for tier_key, tier in config["tiers"].items():
        status = "available" if tier.get("available") else "unavailable"
        lines.append(f"{tier_key}: {tier['name']} ({tier['model']}) — {status}")
    return "\n".join(lines)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport != "stdio":
        logger.warning(
            "SECURITY: Network transport '%s' is not recommended without authentication. "
            "See SECURITY.md for guidance.",
            transport,
        )
    mcp.run(transport=transport)
