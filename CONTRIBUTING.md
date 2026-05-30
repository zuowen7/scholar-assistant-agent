# Contributing

Thanks for your interest in Scholar Assistant. Contributions are welcome.

## Getting Started

```bash
# Clone and install
git clone https://github.com/zuowen7/scholar-assistant.git
cd scholar-assistant
npm install

# Backend
cd python
pip install -r requirements.txt
pytest tests/unit/ -v
```

See [CLAUDE.md](./CLAUDE.md) for a full architecture overview and build commands.

## Development Workflow

1. **Fork** the repo and create a branch from `main`
2. **Write your code** — add tests for new functionality
3. **Run the test suite** before pushing:

```bash
# Python tests
cd python && pytest tests/ -v

# Frontend tests
npx vitest run
```

4. **Submit a PR** with a clear description of the change and why it's needed

## PR Expectations

- Keep PRs focused — one change per PR
- Include tests — backend changes need pytest coverage, frontend changes need vitest
- Run the full test suite locally before pushing
- The CI will run `pytest tests/unit/` and `npx vitest run` automatically

## Where to Start

Good first issues are tagged `good-first-issue`. Areas that could use help:

- **Windows packaging** — test the installer on different Windows versions
- **Provider integration** — add support for more cloud LLM providers in `python/src/translator/cloud_client.py`
- **Frontend polishing** — improve UI/UX in Vue components
- **Documentation** — improve README, add tutorials, translate docs

## Code Style

- Backend: follow PEP 8, use type hints, prefer `dataclass` over `dict`
- Frontend: TypeScript strict mode, Vue 3 Composition API
- No pointless comments — code should be self-documenting
