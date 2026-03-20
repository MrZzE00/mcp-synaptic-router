# Contributing to Synaptic Router

Thank you for your interest in contributing to Synaptic Router.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/mcp-synaptic-router.git
   cd mcp-synaptic-router
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Set up a virtual environment** and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   ```

## Running Tests

```bash
pytest
```

All tests must pass before submitting a pull request.

## Security Rules

These rules are **non-negotiable** for all contributions:

- **Never** add `eval()`, `exec()`, or any form of dynamic code execution.
- **Always** validate all external inputs (prompts, configuration values, API responses).
- **Fail closed**: if unsure about routing, default to the highest tier (Claude).
- **No secrets in code**: API keys and credentials must come from environment variables.
- Review the [Security Policy](SECURITY.md) before contributing.

## Pull Request Requirements

- All existing tests pass (`pytest`).
- New features include corresponding tests.
- Any code that handles new user inputs or external data must undergo a security review.
- Commit messages are clear and descriptive.

## Code Style

- **Python 3.11+** is required.
- **Type hints** are encouraged for all function signatures.
- **Ruff** is used for linting (`ruff check .`).
- Line length limit: **100 characters**.
- Follow existing code patterns and naming conventions.

## Reporting Issues

- Use GitHub Issues for bugs and feature requests.
- For security vulnerabilities, see [SECURITY.md](SECURITY.md).
