<div align="center">

# Synaptic Router

**Hybrid 4-Tier LLM Router -- Right Task, Right Model**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![MCP Server](https://img.shields.io/badge/MCP-Server-blue)](https://modelcontextprotocol.io)
[![Ollama](https://img.shields.io/badge/Ollama-local_inference-black?logo=ollama)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[The Problem](#the-problem) · [The Solution](#the-solution) · [Quick Start](#-quick-start) · [MCP Tools](#-mcp-tools) · [Configuration](#-configuration) · [Security](#-security) · [Troubleshooting](#-troubleshooting)

</div>

---

## The Problem

AI coding assistants send **every single prompt** to expensive cloud APIs -- even trivial tasks like generating boilerplate, writing docstrings, or stubbing out unit tests. A simple `// TODO: add imports` costs the same as a full architecture review. Token budgets drain fast, latency adds up, and your API bill does not distinguish between a one-line completion and a critical security audit.

## The Solution

**Synaptic Router** classifies each prompt by complexity, category, and context size, then routes it to the optimal model tier:

| Tier | Model | Backend | Latency | Use Cases |
|------|-------|---------|---------|-----------|
| **Tier 1** | BitNet | Ollama | <100ms | Autocompletion, naming, imports, basic docstrings |
| **Tier 2** | GLM-4 (9B) | Ollama | <800ms | Function generation, unit tests, refactoring, docs |
| **Tier 2b** | Qwen3-Coder (14B) | Ollama | <1200ms | Large context (>16K tokens), multi-file analysis, PR reviews |
| **Tier 3** | Claude | Anthropic | <5000ms | Security reviews, architecture decisions, complex debugging |

Simple tasks stay local and fast. Critical decisions go to the most capable model. Your API budget is spent where it matters.

---

## Features

- **4-Tier Intelligent Routing** -- Automatic prompt classification routes to the optimal model based on category, token count, and latency requirements
- **Safe Declarative Rule Engine** -- Routing conditions use a structured `field/op/value` format with `all`/`any` combinators; no `eval()` or `exec()` anywhere in the codebase
- **Fail-Closed Security** -- Any rule evaluation error automatically routes to Tier 3 (most secure), never to a less capable model
- **SSRF Protection** -- Ollama host validated against a strict allowlist (`localhost`, `127.0.0.1`, `::1`); remote hosts require an explicit environment variable override
- **Input Validation** -- Prompt size capped at 100K characters, category restricted to a whitelist, empty prompts rejected
- **Keyword-Based Category Detection** -- Automatic classification of security, architecture, and general prompts via keyword matching
- **Structured Logging** -- Timestamped, leveled logs with routing decisions, latency measurements, and error traces
- **MCP Protocol Native** -- Stdio transport for seamless integration with Claude Code and other MCP clients
- **CLI Mode** -- Standalone usage via `python router.py "your prompt"` with JSON output, verbose mode, and category override
- **Extensible Configuration** -- All tiers, models, routing rules, and backends defined in a single `config.yaml`

---

## Architecture

```
                         +-----------------+
                         |   User Prompt   |
                         +--------+--------+
                                  |
                                  v
                      +-----------+----------+
                      |  Input Validation    |
                      |  (size, whitelist)   |
                      +-----------+----------+
                                  |
                                  v
                      +-----------+----------+
                      | Category Classifier  |
                      | (keyword matching)   |
                      +-----------+----------+
                                  |
                                  v
                      +-----------+----------+
                      | Token Estimator      |
                      | (~4 chars/token)     |
                      +-----------+----------+
                                  |
                                  v
                  +---------------+---------------+
                  |    Declarative Rule Engine     |
                  |  field/op/value | all | any    |
                  +---+-----+-----+-----+---+-----+
                      |     |     |         |
                      v     v     v         v
                  +----+ +----+ +-----+ +-------+
                  | T1 | | T2 | | T2b | |  T3   |
                  +--+-+ +--+-+ +--+--+ +---+---+
                     |      |      |        |
                     v      v      v        v
                  +--+------+------+--+  +--+--------+
                  |      Ollama       |  |  Anthropic |
                  | (BitNet/GLM/Qwen) |  |  (Claude)  |
                  +--------+----------+  +------+-----+
                           |                    |
                           +--------+-----------+
                                    |
                                    v
                           +--------+--------+
                           |    Response     |
                           | (tier, model,   |
                           |  latency, text) |
                           +-----------------+
```

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/MrZzE00/synaptic-router.git
cd synaptic-router
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Install Ollama and pull models

```bash
# Install Ollama — https://ollama.com
brew install ollama        # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh   # Linux

# Start the Ollama server
ollama serve &

# Pull the default models
ollama pull glm4:9b
ollama pull qwen2.5-coder:14b-instruct-q4_K_M
```

### 4. Configure MCP in Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "synaptic-router": {
      "type": "stdio",
      "command": "/absolute/path/to/synaptic-router/venv/bin/python",
      "args": ["/absolute/path/to/synaptic-router/mcp_server.py"]
    }
  }
}
```

### 5. Restart Claude Code and test

```
explain_routing({ prompt: "Write unit tests for the auth module" })
```

You should see the routing decision: tier, model, category, and estimated token count.

---

## MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| **`query_local_model`** | `prompt` (required), `category` (optional), `latency_critical` (optional) | Route the prompt to the optimal model and return the response. Security/architecture categories are automatically redirected to Claude (Tier 3). |
| **`explain_routing`** | `prompt` (required), `category` (optional) | Dry-run: show the routing decision (tier, model, category, tokens) without calling any model. Useful for debugging and understanding routing behavior. |
| **`list_available_models`** | _(none)_ | Return all configured tiers with their model name, backend, and availability status. |

### Parameters Reference

| Parameter | Type | Values | Default |
|-----------|------|--------|---------|
| `prompt` | `string` | Any text (max 100K chars) | _(required)_ |
| `category` | `string` | `"security"`, `"architecture"`, `"general"` | Auto-detected via keywords |
| `latency_critical` | `bool` | `true` / `false` | `false` |

### Usage Examples

**Route a code generation task:**
```
query_local_model({ prompt: "Write a Python function to parse CSV files with error handling" })
# -> Routed to tier2 (GLM-4), response in ~500ms
```

**Check where a security prompt would go:**
```
explain_routing({ prompt: "Review this Express route for XSS vulnerabilities" })
# -> Routing: tier3 (Claude) | Category: security | Tokens: 14
```

**Force a category override:**
```
query_local_model({ prompt: "Generate CRUD endpoints", category: "general" })
# -> Routed to tier2 (GLM-4), bypasses auto-detection
```

---

## Routing Rules

Rules are evaluated in order. The first matching rule determines the tier. If no rule matches, the default is Tier 2 (GLM-4).

| # | Rule Name | Condition | Target Tier |
|---|-----------|-----------|-------------|
| 1 | `security_always_cloud` | Category in `[security, auth, vulnerability, permissions]` | Tier 3 (Claude) |
| 2 | `architecture_always_cloud` | Category in `[architecture, design_pattern, api_design, db_schema]` | Tier 3 (Claude) |
| 3 | `large_context_qwen` | Token count > 16,000 | Tier 2b (Qwen) |
| 4 | `short_tokens_bitnet` | Tokens < 200 **AND** latency critical **AND** Tier 1 available | Tier 1 (BitNet) |
| 5 | `critical_complexity_cloud` | Confidence < 0.7 **OR** complexity == critical | Tier 3 (Claude) |
| 6 | `default_glm` | Always true (catch-all) | Tier 2 (GLM-4) |

### Condition Syntax

Rules use a safe declarative format -- no `eval()`, no string interpolation:

```yaml
# Simple condition
condition:
  field: "category"
  op: "in"
  value: ["security", "architecture"]

# Compound AND
condition:
  all:
    - field: "token_count"
      op: "<"
      value: 200
    - field: "latency_critical"
      op: "=="
      value: true

# Compound OR
condition:
  any:
    - field: "confidence"
      op: "<"
      value: 0.7
    - field: "complexity"
      op: "=="
      value: "critical"
```

**Supported operators:** `in`, `not_in`, `==`, `!=`, `<`, `>`, `<=`, `>=`

---

## Configuration

### config.yaml Structure

```yaml
tiers:
  tier1:
    name: "BitNet"
    model: "bitnet-b1.58-2b4t"
    available: false              # Enable when model is pulled
    backend: "ollama"
    max_tokens: 200
  tier2:
    name: "GLM-4"
    model: "glm4:9b"
    available: true
    backend: "ollama"
  # ... tier2b, tier3

routing:
  rules: [...]                    # Evaluated in order, first match wins

ollama:
  host: "http://localhost:11434"
  timeout_seconds: 120

anthropic:
  timeout_seconds: 30
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | API key for Tier 3 (Claude) routing. Required only if prompts reach Tier 3. | _(none)_ |
| `SYNAPTIC_LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `SYNAPTIC_ALLOW_REMOTE_OLLAMA` | Set to `1` to allow non-localhost Ollama hosts (bypasses SSRF protection). | _(disabled)_ |
| `MCP_TRANSPORT` | MCP transport mode. Only `stdio` is recommended for production. | `stdio` |

### IDE Setup

<details>
<summary><strong>Claude Code</strong> (~/.claude.json)</summary>

```json
{
  "mcpServers": {
    "synaptic-router": {
      "type": "stdio",
      "command": "/absolute/path/to/synaptic-router/venv/bin/python",
      "args": ["/absolute/path/to/synaptic-router/mcp_server.py"]
    }
  }
}
```

</details>

<details>
<summary><strong>VS Code / Cline</strong> (.vscode/mcp.json)</summary>

```json
{
  "mcp": {
    "servers": {
      "synaptic-router": {
        "type": "stdio",
        "command": "/absolute/path/to/synaptic-router/venv/bin/python",
        "args": ["/absolute/path/to/synaptic-router/mcp_server.py"]
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Cursor</strong> (~/.cursor/mcp.json)</summary>

```json
{
  "mcpServers": {
    "synaptic-router": {
      "command": "/absolute/path/to/synaptic-router/venv/bin/python",
      "args": ["/absolute/path/to/synaptic-router/mcp_server.py"]
    }
  }
}
```

</details>

---

## Security

Security is a core design principle, not an afterthought. Key safeguards:

- **No `eval()` or `exec()`** -- Routing conditions use a declarative `field/op/value` engine with a strict operator whitelist
- **Fail-closed routing** -- Any rule evaluation error routes to Tier 3 (Claude), never to a less capable local model
- **SSRF protection** -- Ollama host validated against `localhost`/`127.0.0.1`/`::1`; remote hosts require explicit `SYNAPTIC_ALLOW_REMOTE_OLLAMA=1`
- **Input validation** -- Prompt size capped at 100K characters, category restricted to `{security, architecture, general}`, empty prompts rejected
- **Config path restriction** -- Configuration files must reside within the project directory; path traversal is blocked
- **Transport warning** -- Non-stdio transports log a security warning recommending authentication

> For full details, see [SECURITY.md](SECURITY.md).

---

## CLI Usage

The router can also be used standalone from the command line:

```bash
# Basic usage
python router.py "Write a function to sort a list of dictionaries by key"

# Force a category
python router.py "Review this auth middleware" --category security

# Verbose output (shows routing decision)
python router.py "Generate unit tests for utils.py" --verbose

# Full JSON response (tier, model, latency, tokens, response)
python router.py "Explain this function" --json

# Prioritize latency (activates BitNet if available)
python router.py "import os" --latency-critical

# Use alternative config
python router.py "Hello world" --config ./custom-config.yaml
```

---

## Troubleshooting

**Ollama connection refused**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags
# If not running:
ollama serve &
```

**Model not found in Ollama**
```bash
# List installed models
ollama list
# Pull missing models
ollama pull glm4:9b
ollama pull qwen2.5-coder:14b-instruct-q4_K_M
```

**ANTHROPIC_API_KEY not set (Tier 3 fails)**
```bash
# Export the key in your shell profile
export ANTHROPIC_API_KEY="sk-ant-..."
# Or set it in your IDE's MCP server env config
```

**MCP server does not appear in Claude Code**
```bash
# Verify the Python path is absolute and correct
/absolute/path/to/synaptic-router/venv/bin/python -c "import mcp; print('OK')"
# Check that mcp_server.py is accessible
/absolute/path/to/synaptic-router/venv/bin/python /absolute/path/to/synaptic-router/mcp_server.py
# Restart Claude Code after editing ~/.claude.json
```

**All prompts route to Tier 3**
```bash
# Check category detection
python router.py "your prompt" --verbose
# If the prompt contains security/architecture keywords, Tier 3 is expected
# To override: use --category general or pass category="general" in MCP
```

---

## Contributing

Contributions are welcome. Please open an issue to discuss your idea before submitting a pull request.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

[MIT](LICENSE)

[![With love by Zenika](https://img.shields.io/badge/With%20%E2%9D%A4%EF%B8%8F%20by-Zenika-b51432.svg)](https://oss.zenika.com)
