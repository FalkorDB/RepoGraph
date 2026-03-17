"""Team-level graph model — maps developers to teams for aggregate insights."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from repograph.core.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class TeamConfig:
    """Configuration for a single team."""

    name: str
    members: list[str]  # list of developer emails


def load_teams_from_yaml(path: str | Path) -> list[TeamConfig]:
    """Load team definitions from a YAML file.

    Expected format:
        teams:
          - name: Backend
            members:
              - alice@example.com
              - bob@example.com
          - name: Frontend
            members:
              - carol@example.com
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Team config not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or "teams" not in data:
        raise ValueError(f"Invalid team config: expected 'teams' key in {path}")

    teams: list[TeamConfig] = []
    for entry in data["teams"]:
        if "name" not in entry or "members" not in entry:
            logger.warning("Skipping invalid team entry: %s", entry)
            continue
        teams.append(TeamConfig(name=entry["name"], members=entry["members"]))

    return teams


def build_team_graph(db: DatabaseManager, teams: list[TeamConfig]) -> dict[str, int]:
    """Create Team nodes and MEMBER_OF relationships in the graph."""
    stats = {"teams": 0, "memberships": 0}

    for team in teams:
        db.query(
            "MERGE (t:Team {name: $name})",
            params={"name": team.name},
        )
        stats["teams"] += 1

        for email in team.members:
            result = db.query(
                "MATCH (d:Developer {email: $email}), (t:Team {name: $team}) "
                "MERGE (d)-[:MEMBER_OF]->(t) "
                "RETURN d.name",
                params={"email": email, "team": team.name},
            )
            if result.result_set:
                stats["memberships"] += 1
            else:
                logger.warning("Developer %s not found in graph for team %s", email, team.name)

    logger.info("Built team graph: %s", stats)
    return stats


def auto_detect_teams(db: DatabaseManager, domain_grouping: bool = True) -> list[TeamConfig]:
    """Auto-detect teams from developer email domains.

    Groups developers by email domain (e.g., @backend.company.com → Backend team).
    Falls back to a single "All" team if domains are uniform.
    """
    result = db.query("MATCH (d:Developer) RETURN d.email, d.name ORDER BY d.email")

    if not result.result_set:
        return []

    if domain_grouping:
        domain_map: dict[str, list[str]] = {}
        for row in result.result_set:
            email = row[0]
            domain = email.split("@")[-1] if "@" in email else "unknown"
            domain_map.setdefault(domain, []).append(email)

        # If all same domain, don't split into teams
        if len(domain_map) <= 1:
            return [
                TeamConfig(
                    name="All",
                    members=[row[0] for row in result.result_set],
                )
            ]

        return [
            TeamConfig(name=domain.split(".")[0].title(), members=members)
            for domain, members in domain_map.items()
        ]

    return [
        TeamConfig(
            name="All",
            members=[row[0] for row in result.result_set],
        )
    ]


# ---------------------------------------------------------------------------
# Team-level queries
# ---------------------------------------------------------------------------


@dataclass
class TeamBusFactor:
    """Bus factor analysis at team level."""

    team: str
    member_count: int
    modules_covered: int
    exclusive_modules: list[str]  # modules ONLY this team knows


@dataclass
class TeamSilo:
    """A module that is only known by one team."""

    module: str
    owning_team: str
    experts_in_team: int
    file_count: int


def query_team_bus_factor(db: DatabaseManager, min_score: float = 0.5) -> list[TeamBusFactor]:
    """Compute bus factor at team level.

    Finds modules exclusively known by a single team — a team-level knowledge silo.
    Uses multi-hop traversal: Team ← Developer → KNOWS → File → PART_OF → Module
    """
    result = db.query(
        "MATCH (t:Team)<-[:MEMBER_OF]-(d:Developer)-[k:KNOWS]->(f:File)-[:PART_OF]->(m:Module) "
        "WHERE k.score >= $min_score "
        "WITH t, collect(DISTINCT m.path) AS modules, count(DISTINCT d) AS members "
        "RETURN t.name, members, size(modules), modules",
        params={"min_score": min_score},
    )

    team_modules: dict[str, set[str]] = {}
    team_data: dict[str, tuple[int, int]] = {}

    if result.result_set:
        for row in result.result_set:
            team_name, members, mod_count, modules = row
            team_modules[team_name] = set(modules) if isinstance(modules, list) else set()
            team_data[team_name] = (members, mod_count)

    # Find exclusive modules per team
    results: list[TeamBusFactor] = []
    all_teams = list(team_modules.keys())
    for team_name in all_teams:
        my_modules = team_modules[team_name]
        other_modules = set()
        for other_team, other_mods in team_modules.items():
            if other_team != team_name:
                other_modules |= other_mods

        exclusive = sorted(my_modules - other_modules)
        members, mod_count = team_data.get(team_name, (0, 0))

        results.append(
            TeamBusFactor(
                team=team_name,
                member_count=members,
                modules_covered=mod_count,
                exclusive_modules=exclusive,
            )
        )

    return sorted(results, key=lambda x: len(x.exclusive_modules), reverse=True)


def query_team_silos(db: DatabaseManager, min_score: float = 0.5) -> list[TeamSilo]:
    """Find modules that are knowledge silos at the team level.

    A team silo is a module where all knowledgeable developers belong to one team.
    """
    result = db.query(
        "MATCH (d:Developer)-[k:KNOWS]->(f:File)-[:PART_OF]->(m:Module) "
        "WHERE k.score >= $min_score "
        "OPTIONAL MATCH (d)-[:MEMBER_OF]->(t:Team) "
        "WITH m, collect(DISTINCT t.name) AS teams, "
        "count(DISTINCT d) AS expert_count, count(DISTINCT f) AS file_count "
        "WHERE size(teams) = 1 "
        "RETURN m.path, teams[0], expert_count, file_count "
        "ORDER BY file_count DESC",
        params={"min_score": min_score},
    )

    silos: list[TeamSilo] = []
    if result.result_set:
        for row in result.result_set:
            silos.append(
                TeamSilo(
                    module=row[0],
                    owning_team=row[1] or "Unassigned",
                    experts_in_team=row[2],
                    file_count=row[3],
                )
            )

    return silos
