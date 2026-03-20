# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < latest | :x:               |

Only the latest release receives security updates. Please upgrade to the latest version before reporting issues.

## Reporting Vulnerabilities

**Do not open a public issue for security vulnerabilities.**

Instead, use one of the following:

- **GitHub Security Advisories**: Open a private advisory at [https://github.com/MrZzE00/mcp-synaptic-router/security/advisories/new](https://github.com/MrZzE00/mcp-synaptic-router/security/advisories/new)
- **Email**: Contact the maintainer directly via GitHub profile

You should receive an acknowledgment within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Security Design Decisions

### No Dynamic Code Execution

All uses of `eval()`, `exec()`, and similar dynamic code execution have been deliberately removed from the codebase. Routing conditions are evaluated using **declarative keyword matching** only. This eliminates an entire class of code injection vulnerabilities.

### Declarative Routing Conditions

Routing rules in `config.yaml` use simple keyword lists and category strings rather than arbitrary expressions. The router matches prompts against predefined keywords — no user input is ever interpreted as code.

### SSRF Protection

When connecting to Ollama backends:
- By default, only `localhost` / `127.0.0.1` connections are permitted.
- Remote Ollama endpoints require the explicit environment variable `SYNAPTIC_ALLOW_REMOTE_OLLAMA=true`.
- All HTTP requests use timeouts to prevent hanging connections.

### Fail-Closed Routing

If the router cannot determine the appropriate tier for a prompt, it **defaults to the highest tier (Claude/Anthropic)**. This ensures that sensitive prompts are never accidentally routed to a less capable or less secure local model.

### Input Validation

- Prompt length is bounded before processing.
- Category values are validated against an allowlist.
- Configuration files are validated at startup.

## Transport Security

### Recommended: stdio Transport

The MCP server is designed to run over **stdio** transport, communicating directly with the Claude Code client process. This avoids network exposure entirely.

### Network Transport (Advanced)

If you run the server over HTTP/SSE transport:
- Always use TLS (HTTPS).
- Add authentication middleware — the MCP server does not include built-in auth.
- Restrict access to trusted networks or localhost.

## Environment Variables

| Variable | Sensitivity | Notes |
|----------|-------------|-------|
| `ANTHROPIC_API_KEY` | **High** | Never commit to version control. Use `.env` files (excluded via `.gitignore`) or system keychain. |
| `SYNAPTIC_ALLOW_REMOTE_OLLAMA` | Medium | Only set to `true` if you trust the remote Ollama endpoint. |

## Dependencies

- All dependencies are **pinned to minimum versions** in `pyproject.toml`.
- Run `pip audit` regularly to check for known vulnerabilities.
- Review dependency updates before upgrading, especially for `httpx` and `anthropic`.
