"""Flask web API and D3.js visualization server for RepoGraph."""

from __future__ import annotations

import logging
import os
import subprocess

from flask import Flask, jsonify, render_template, request

from repograph.core.config import FalkorDBConfig
from repograph.core.database import DatabaseManager
from repograph.core.queries import (
    query_blast_radius,
    query_bus_factor,
    query_developer_overlap,
    query_graph_summary,
    query_knowledge_silos,
    query_module_coupling,
    query_reviewers,
    query_risk_hotspots,
)
from repograph.core.teams import query_team_bus_factor, query_team_silos

logger = logging.getLogger(__name__)


def create_app(config: FalkorDBConfig | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    db_config = config or FalkorDBConfig.from_env()
    db = DatabaseManager(db_config)

    @app.before_request
    def ensure_connection():
        if not db.health_check():
            db.connect()

    # -----------------------------------------------------------------------
    # Dashboard
    # -----------------------------------------------------------------------

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    # -----------------------------------------------------------------------
    # REST API endpoints
    # -----------------------------------------------------------------------

    @app.route("/api/summary")
    def api_summary():
        return jsonify(query_graph_summary(db))

    @app.route("/api/bus-factor")
    def api_bus_factor():
        module = request.args.get("module")
        min_score = float(request.args.get("min_score", "0.5"))
        results = query_bus_factor(db, module=module, min_score=min_score)
        return jsonify(
            [
                {
                    "module": r.module,
                    "bus_factor": r.bus_factor,
                    "file_count": r.file_count,
                    "experts": r.experts,
                }
                for r in results
            ]
        )

    @app.route("/api/blast-radius/<path:file_path>")
    def api_blast_radius(file_path: str):
        depth = int(request.args.get("depth", "3"))
        depth = max(1, min(depth, 5))
        result = query_blast_radius(db, file_path=file_path, max_depth=depth)
        return jsonify(
            {
                "source_file": result.source_file,
                "affected_files": result.affected_files,
                "affected_modules": result.affected_modules,
                "total_affected": len(result.affected_files),
            }
        )

    @app.route("/api/reviewers/<path:file_path>")
    def api_reviewers(file_path: str):
        limit = int(request.args.get("limit", "5"))
        results = query_reviewers(db, file_path=file_path, limit=limit)
        return jsonify(
            [
                {
                    "name": r.name,
                    "email": r.email,
                    "score": r.score,
                    "commit_count": r.commit_count,
                }
                for r in results
            ]
        )

    @app.route("/api/silos")
    def api_silos():
        max_experts = int(request.args.get("max_experts", "2"))
        min_score = float(request.args.get("min_score", "0.5"))
        results = query_knowledge_silos(db, max_experts=max_experts, min_score=min_score)
        return jsonify(
            [
                {
                    "module": r.module,
                    "expert_count": r.expert_count,
                    "experts": r.experts,
                    "file_count": r.file_count,
                    "risk_level": r.risk_level,
                }
                for r in results
            ]
        )

    @app.route("/api/coupling")
    def api_coupling():
        min_strength = int(request.args.get("min_strength", "3"))
        results = query_module_coupling(db, min_strength=min_strength)
        return jsonify(
            [
                {
                    "module_a": r.module_a,
                    "module_b": r.module_b,
                    "coupling_strength": r.coupling_strength,
                    "shared_files": r.shared_files,
                }
                for r in results
            ]
        )

    @app.route("/api/risks")
    def api_risks():
        min_score = float(request.args.get("min_score", "0.5"))
        results = query_risk_hotspots(db, min_score=min_score)
        return jsonify(
            [
                {
                    "module": r.module,
                    "bus_factor": r.bus_factor,
                    "change_frequency": r.change_frequency,
                    "risk_score": r.risk_score,
                    "risk_level": r.risk_level,
                }
                for r in results
            ]
        )

    @app.route("/api/overlap")
    def api_overlap():
        min_shared = int(request.args.get("min_shared", "3"))
        results = query_developer_overlap(db, min_shared=min_shared)
        return jsonify(
            [
                {
                    "dev_a": r.dev_a,
                    "dev_b": r.dev_b,
                    "shared_files": r.shared_files,
                    "overlap_score": r.overlap_score,
                }
                for r in results
            ]
        )

    @app.route("/api/teams/bus-factor")
    def api_team_bus_factor():
        min_score = float(request.args.get("min_score", "0.5"))
        results = query_team_bus_factor(db, min_score=min_score)
        return jsonify(
            [
                {
                    "team": r.team,
                    "member_count": r.member_count,
                    "modules_covered": r.modules_covered,
                    "exclusive_modules": r.exclusive_modules,
                }
                for r in results
            ]
        )

    @app.route("/api/teams/silos")
    def api_team_silos():
        min_score = float(request.args.get("min_score", "0.5"))
        results = query_team_silos(db, min_score=min_score)
        return jsonify(
            [
                {
                    "module": r.module,
                    "owning_team": r.owning_team,
                    "experts_in_team": r.experts_in_team,
                    "file_count": r.file_count,
                }
                for r in results
            ]
        )

    @app.route("/api/graph")
    def api_graph():
        """Return the full graph as D3.js-compatible nodes and links."""
        nodes = []
        links = []
        node_ids = set()

        # Developers
        dev_result = db.query("MATCH (d:Developer) RETURN d.name, d.email")
        if dev_result.result_set:
            for row in dev_result.result_set:
                nid = f"dev:{row[1]}"
                nodes.append({"id": nid, "label": row[0], "type": "developer", "email": row[1]})
                node_ids.add(nid)

        # Modules
        mod_result = db.query("MATCH (m:Module) RETURN m.path, m.name")
        if mod_result.result_set:
            for row in mod_result.result_set:
                nid = f"mod:{row[0]}"
                nodes.append({"id": nid, "label": row[1], "type": "module", "path": row[0]})
                node_ids.add(nid)

        # Teams
        team_result = db.query("MATCH (t:Team) RETURN t.name")
        if team_result.result_set:
            for row in team_result.result_set:
                nid = f"team:{row[0]}"
                nodes.append({"id": nid, "label": row[0], "type": "team"})
                node_ids.add(nid)

        # KNOWS relationships (developer -> module, aggregated)
        knows_result = db.query(
            "MATCH (d:Developer)-[k:KNOWS]->(f:File)-[:PART_OF]->(m:Module) "
            "WITH d, m, sum(k.score) AS total "
            "WHERE total >= 1.0 "
            "RETURN d.email, m.path, total"
        )
        if knows_result.result_set:
            for row in knows_result.result_set:
                src, tgt = f"dev:{row[0]}", f"mod:{row[1]}"
                if src in node_ids and tgt in node_ids:
                    links.append(
                        {"source": src, "target": tgt, "type": "knows", "weight": round(row[2], 1)}
                    )

        # CO_CHANGED_WITH between modules (aggregated)
        coupling_result = db.query(
            "MATCH (f1:File)-[r:CO_CHANGED_WITH]->(f2:File), "
            "(f1)-[:PART_OF]->(m1:Module), (f2)-[:PART_OF]->(m2:Module) "
            "WHERE m1 <> m2 "
            "WITH m1, m2, sum(r.frequency) AS strength "
            "WHERE strength >= 3 "
            "RETURN m1.path, m2.path, strength"
        )
        if coupling_result.result_set:
            seen = set()
            for row in coupling_result.result_set:
                pair = tuple(sorted([row[0], row[1]]))
                if pair not in seen:
                    seen.add(pair)
                    src, tgt = f"mod:{pair[0]}", f"mod:{pair[1]}"
                    if src in node_ids and tgt in node_ids:
                        links.append(
                            {"source": src, "target": tgt, "type": "coupling", "weight": row[2]}
                        )

        # MEMBER_OF relationships
        member_result = db.query(
            "MATCH (d:Developer)-[:MEMBER_OF]->(t:Team) RETURN d.email, t.name"
        )
        if member_result.result_set:
            for row in member_result.result_set:
                src, tgt = f"dev:{row[0]}", f"team:{row[1]}"
                if src in node_ids and tgt in node_ids:
                    links.append({"source": src, "target": tgt, "type": "member_of", "weight": 1})

        return jsonify({"nodes": nodes, "links": links})

    # -----------------------------------------------------------------------
    # Webhook endpoint
    # -----------------------------------------------------------------------

    @app.route("/webhook/push", methods=["POST"])
    def webhook_push():
        """Handle GitHub push webhook to trigger re-analysis.

        Configure in GitHub: Settings → Webhooks → Payload URL: http://host:5001/webhook/push
        Content type: application/json, Events: Just the push event.
        """
        from repograph.core.config import AnalysisConfig
        from repograph.core.git_analyzer import analyze_repository
        from repograph.core.graph_builder import build_graph
        from repograph.core.schema import setup_schema

        payload = request.get_json(silent=True)
        if not payload:
            return jsonify({"error": "No payload"}), 400

        repo_path = os.environ.get("REPOGRAPH_REPO_PATH")
        if not repo_path:
            return jsonify({"error": "REPOGRAPH_REPO_PATH not configured"}), 500

        try:
            # Pull latest changes
            subprocess.run(["git", "pull"], cwd=repo_path, capture_output=True, timeout=30)

            setup_schema(db)
            db.clear_graph()
            analysis = analyze_repository(repo_path, AnalysisConfig())
            build_graph(db, analysis)
            summary = query_graph_summary(db)

            return jsonify({"status": "ok", "summary": summary})

        except Exception as e:
            logger.error("Webhook processing failed: %s", e)
            return jsonify({"error": str(e)}), 500

    return app


def run_server(host: str = "0.0.0.0", port: int = 5001, debug: bool = False) -> None:
    """Run the web server."""
    app = create_app()
    app.run(host=host, port=port, debug=debug)
