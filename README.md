# RepoGraph 📊

**Git repository intelligence powered by FalkorDB graph analysis.**

RepoGraph turns your git history into a knowledge graph, answering questions that are nearly impossible with traditional tools: *Who really knows this code? What breaks if this file changes? Where are the knowledge silos that put our team at risk?*

## Why Graph?

Your codebase is a web of relationships: developers → commit → modify → files → belong to → modules. Traditional tools give you flat lists (git log, git blame). RepoGraph gives you **graph intelligence**:

- **🚌 Bus Factor**: Not just "who committed" but "who has deep, recent knowledge across an entire module" — computed through multi-hop graph traversal
- **💥 Blast Radius**: Variable-length path traversal through co-change relationships — "if you change this file, these 47 other files historically change too, across 3 modules"
- **🏝️ Knowledge Silos**: Subgraph aggregation to find modules where expertise is concentrated in 1-2 people
- **🔗 Module Coupling**: Cross-module co-change pattern detection — hidden dependencies your architecture diagram doesn't show
- **⚠️ Risk Hotspots**: Combines graph topology (bus factor) with temporal analysis (change frequency) to surface the most dangerous areas

These queries involve multi-hop traversals, aggregation over subgraphs, and bipartite pattern matching — operations that would require recursive CTEs and multiple round-trips in SQL, but are natural in FalkorDB's Cypher.

## Quick Start

```bash
# Start FalkorDB
docker-compose up -d falkordb

# Install RepoGraph
pip install .

# Load demo data (no git repo needed)
repograph seed

# Explore the insights
repograph bus-factor
repograph silos
repograph blast-radius src/core/engine.py
repograph reviewers src/api/routes.py
repograph coupling
repograph risks
repograph overlap
```

### Analyze Your Own Repository

```bash
repograph analyze /path/to/your/repo
repograph bus-factor
repograph blast-radius src/main.py --depth 3
repograph reviewers src/main.py
```

## Example Output

### Bus Factor Report
```
🚌 Bus Factor Report
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Module       ┃  Bus Factor  ┃ Files ┃ Top Experts                                       ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ src/billing  │     🔴 1     │   6   │ Carol Singh (8.5)                                 │
│ src/auth     │     🟡 2     │   4   │ Alice Chen (7.2), Bob Martinez (3.1)               │
│ src/core     │     🟢 5     │  12   │ Grace Liu (15.4), Bob Martinez (12.8), Carol (9.1) │
└──────────────┴──────────────┴───────┴───────────────────────────────────────────────────━━┛
```

### Blast Radius
```
💥 Blast Radius Analysis
┌──────────────────────────────┬──────────┬──────────┐
│ File                         │ Distance │ Risk     │
├──────────────────────────────┼──────────┼──────────┤
│ src/core/pipeline.py         │    1     │ Direct   │
│ src/core/cache.py            │    1     │ Direct   │
│ src/api/routes.py            │    2     │ Indirect │
│ src/services/notifications.py│    3     │Transitive│
└──────────────────────────────┴──────────┴──────────┘
Affected modules: src/core, src/api, src/services
Total affected files: 18
```

## Graph Schema

```
(:Developer {name, email})
  │
  ├──[:AUTHORED]──▶ (:Commit {hash, message, timestamp})
  │                    │
  │                    ├──[:MODIFIED {additions, deletions}]──▶ (:File {path, extension, language})
  │                    │                                            │
  │                    └──[:IN_REPO]──▶ (:Repository {name, path})  ├──[:BELONGS_TO]──▶ (:Repository)
  │                                                                 │
  ├──[:KNOWS {score, last_touched, commit_count}]───────────────────┤
  │                                                                 │
  ├──[:MEMBER_OF]──▶ (:Team {name})                                 ├──[:PART_OF]──▶ (:Module {name, path, depth})
  │                                                                 │                    │
  │                                                                 │                    └──[:CHILD_OF]──▶ (:Module)
  │                                                                 │
  │                                                                 └──[:CO_CHANGED_WITH {frequency}]──▶ (:File)
  │
(:Snapshot {snapshot_id, timestamp, avg_bus_factor, silo_count, high_risk_count, ...})
(:ModuleSnapshot {snapshot_id, timestamp, module, bus_factor, risk_score, risk_level})
```

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐
│  Git Repo   │───▶│ Git Analyzer │───▶│   Graph     │───▶│ FalkorDB │
│  (.git)     │    │ (GitPython)  │    │   Builder   │    │          │
└─────────────┘    └──────────────┘    └─────────────┘    └──────────┘
                                                                │
┌─────────────┐    ┌──────────────┐    ┌─────────────┐         │
│  Terminal   │◀───│  Formatters  │◀───│   Queries   │◀────────┘
│  (Rich)     │    │  (Rich)      │    │  (Cypher)   │
└─────────────┘    └──────────────┘    └─────────────┘
```

## Star Cypher Queries

### 1. Blast Radius (Variable-Length Path Traversal)
```cypher
MATCH path = (source:File {path: $path})-[:CO_CHANGED_WITH*1..3]-(target:File)
WHERE source <> target
WITH target, min(length(path)) AS distance
RETURN target.path, distance
ORDER BY distance
```

### 2. Bus Factor (Subgraph Aggregation)
```cypher
MATCH (d:Developer)-[k:KNOWS]->(f:File)-[:PART_OF]->(m:Module)
WHERE k.score >= $min_score
WITH m, d, sum(k.score) AS total_score, count(f) AS files_known
WITH m, collect({name: d.name, score: total_score}) AS experts
RETURN m.path, size(experts) AS bus_factor, experts
ORDER BY bus_factor ASC
```

### 3. Module Coupling (Cross-Subgraph Aggregation)
```cypher
MATCH (f1:File)-[r:CO_CHANGED_WITH]->(f2:File),
      (f1)-[:PART_OF]->(m1:Module), (f2)-[:PART_OF]->(m2:Module)
WHERE m1 <> m2
WITH m1, m2, sum(r.frequency) AS coupling
RETURN m1.path, m2.path, coupling
ORDER BY coupling DESC
```

### 4. Risk Hotspots (Topology + Temporal)
```cypher
MATCH (m:Module)<-[:PART_OF]-(f:File)<-[:MODIFIED]-(c:Commit)
WITH m, count(DISTINCT c) AS change_freq
MATCH (d:Developer)-[k:KNOWS]->(f2:File)-[:PART_OF]->(m)
WHERE k.score >= $min_score
WITH m, change_freq, count(DISTINCT d) AS bus_factor
RETURN m.path, bus_factor, change_freq,
       toFloat(change_freq) / bus_factor AS risk
ORDER BY risk DESC
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `repograph analyze <path>` | Analyze a git repository and build the graph |
| `repograph seed` | Load demo data for testing |
| `repograph bus-factor` | Show bus factor per module |
| `repograph blast-radius <file>` | Show change impact for a file |
| `repograph reviewers <file>` | Suggest code reviewers |
| `repograph silos` | Find knowledge silos |
| `repograph coupling` | Show implicit module coupling |
| `repograph risks` | Identify risk hotspots |
| `repograph overlap` | Show developer knowledge overlap |
| `repograph summary` | Show graph statistics |
| `repograph clear` | Clear all graph data |
| `repograph teams <file>` | Load team definitions from YAML |
| `repograph team-bus-factor` | Show bus factor at team level |
| `repograph team-silos` | Find team-level knowledge silos |
| `repograph import-reviews <repo>` | Import GitHub PR reviews as knowledge signal |
| `repograph web` | Start the web dashboard with D3.js visualization |
| `repograph snapshot` | Take a point-in-time snapshot of graph health metrics |
| `repograph trends` | Show metric trends from snapshot history |
| `repograph snapshot-history` | List all snapshots taken so far |
| `repograph repos` | List all repositories in the graph |
| `repograph cross-repo-experts` | Find developers with expertise across repos |

## Web Dashboard

RepoGraph includes an interactive web dashboard with D3.js force-directed graph visualization:

```bash
# Start the dashboard (requires FalkorDB with data)
repograph web --port 5001

# Or with Docker Compose
docker-compose up -d
# Open http://localhost:5001
```

The dashboard includes:
- **Interactive force-directed graph** — developers, modules, and teams as nodes; knowledge, coupling, and membership as edges
- **Tabbed insights panel** — Overview, Bus Factor, Risks, Coupling, Teams
- **Search and filtering** — find developers, modules, or files
- **Node highlighting** — click a module to highlight its connections
- **Dark theme** — GitHub-inspired design

## Team-Level Analysis

Map developers to teams for aggregate insights:

```yaml
# teams.yml
teams:
  - name: Backend
    members: [alice@example.com, bob@example.com]
  - name: Frontend
    members: [carol@example.com]
```

```bash
# Load team definitions
repograph teams teams.yml

# Team-level queries
repograph team-bus-factor    # Which teams own exclusive modules?
repograph team-silos         # Which modules are known by only one team?
```

## Temporal Trend Analysis

Track how your codebase health evolves over time by taking periodic snapshots:

```bash
# Take a snapshot of current metrics
repograph snapshot

# View snapshot history
repograph snapshot-history

# See metric trends (requires 2+ snapshots)
repograph trends
```

Each snapshot captures: average bus factor, silo count, high-risk module count, and per-module metrics. The trend engine detects whether metrics are **improving**, **degrading**, or **stable**.

**API endpoints:**
- `POST /api/snapshots` — take a new snapshot
- `GET /api/snapshots` — list snapshot history
- `GET /api/trends` — get metric trends with direction indicators

## Multi-Repository Support

Analyze multiple repositories into a single graph to find cross-repo experts:

```bash
# Analyze multiple repos with distinct names
repograph analyze /path/to/frontend --repo-name frontend
repograph analyze /path/to/backend --repo-name backend
repograph analyze /path/to/shared-lib --repo-name shared-lib

# List all repositories in the graph
repograph repos

# Find developers who bridge knowledge across repos
repograph cross-repo-experts --min-repos 2
```

Cross-repo queries traverse: `Developer → KNOWS → File → BELONGS_TO → Repository` — a powerful multi-hop graph traversal that identifies people critical to your organization's cross-team knowledge sharing.

**API endpoints:**
- `GET /api/repos` — list repositories
- `GET /api/repos/<name>/summary` — get repo-specific stats
- `GET /api/cross-repo-experts` — find multi-repo experts

## Installation from PyPI

```bash
pip install repograph
```

Requires a running FalkorDB instance. The easiest way is via Docker:

```bash
docker run -p 6379:6379 falkordb/falkordb:latest
```

## GitHub Integration

### PR Review Import
PR reviews are a strong signal of code knowledge — someone who reviewed code understands it:

```bash
# Import PR reviews as knowledge signal (requires gh CLI)
repograph import-reviews owner/repo --limit 100
```

### Reviewer Bot
A GitHub Action (`.github/workflows/reviewer-bot.yml`) auto-suggests reviewers on PRs based on the knowledge graph. It posts a comment listing the best reviewers for each changed file.

### Webhook for Continuous Analysis
The web server includes a webhook endpoint for automatic re-analysis on push:

```
POST http://host:5001/webhook/push
```

Configure in GitHub: Settings → Webhooks → Payload URL → `http://host:5001/webhook/push`.

## Configuration

All settings can be configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FALKORDB_HOST` | `localhost` | FalkorDB server host |
| `FALKORDB_PORT` | `6379` | FalkorDB server port |
| `FALKORDB_PASSWORD` | (none) | FalkorDB password |
| `REPOGRAPH_GRAPH_NAME` | `repograph` | Name of the graph in FalkorDB |
| `REPOGRAPH_MAX_COMMITS` | `5000` | Maximum commits to analyze |
| `REPOGRAPH_KNOWLEDGE_DECAY_DAYS` | `365` | Days until knowledge score decays to ~37% |
| `REPOGRAPH_MODULE_DEPTH` | `2` | Directory depth for module inference |
| `REPOGRAPH_MIN_KNOWLEDGE_SCORE` | `0.1` | Minimum score to create KNOWS relationship |

## Development

```bash
# Install dev dependencies
make dev

# Run all tests
make test

# Run only unit tests (no FalkorDB needed)
make test-unit

# Run integration tests (requires FalkorDB)
make test-integration

# Lint
make lint

# Format
make format

# Coverage report
make test-coverage
```

## Project Structure

```
repograph/
├── __init__.py
├── cli/
│   ├── __init__.py
│   └── main.py              # Click CLI commands
├── core/
│   ├── __init__.py
│   ├── config.py             # Configuration management
│   ├── database.py           # FalkorDB connection manager
│   ├── git_analyzer.py       # Git history parser
│   ├── graph_builder.py      # Graph population from git data
│   ├── multi_repo.py         # Multi-repository support
│   ├── queries.py            # Core Cypher queries
│   ├── schema.py             # Graph schema setup
│   ├── seed.py               # Demo data generator
│   ├── snapshots.py          # Temporal trend analysis
│   └── teams.py              # Team model and queries
├── integrations/
│   ├── __init__.py
│   └── github.py             # GitHub PR review integration
├── utils/
│   ├── __init__.py
│   └── formatters.py         # Rich terminal formatters
└── web/
    ├── __init__.py
    ├── app.py                # Flask web API
    └── templates/
        └── dashboard.html    # D3.js interactive dashboard
tests/
├── unit/                      # Unit tests (no FalkorDB needed)
└── integration/               # Integration tests (require FalkorDB)
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Run tests (`make test`)
4. Run linter (`make lint`)
5. Commit with conventional commits (`feat(queries): add team-level bus factor`)
6. Push and open a PR

## License

MIT — see [LICENSE](LICENSE).
