"""Enterprise digital twin — organizational operational state."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.exposure.scoring import ExposureScoringEngine
from app.knowledge.graph import KnowledgeGraphService
from app.models.obligation import Obligation
from app.models.workflow_state import WorkflowState


class EnterpriseDigitalTwin:
    def __init__(self, db: Session) -> None:
        self._db = db

    def snapshot(self) -> dict:
        obligations = (
            self._db.query(Obligation)
            .filter(Obligation.status.notin_(("completed", "validated")))
            .limit(200)
            .all()
        )
        workflows = (
            self._db.query(WorkflowState)
            .filter(WorkflowState.current_stage.in_(("active", "escalated")))
            .all()
        )
        exposure = ExposureScoringEngine(self._db).enterprise_scores()

        teams: dict[str, dict] = {}
        for ob in obligations:
            t = ob.owner_team
            if t not in teams:
                teams[t] = {"obligations": 0, "overdue": 0, "risk_levels": []}
            teams[t]["obligations"] += 1
            if ob.status == "overdue":
                teams[t]["overdue"] += 1
            teams[t]["risk_levels"].append(ob.risk_level)

        nodes = [
            {"id": f"team:{k}", "type": "team", "label": k, **v}
            for k, v in teams.items()
        ]
        for ob in obligations[:50]:
            nodes.append(
                {
                    "id": f"obligation:{ob.id}",
                    "type": "obligation",
                    "label": ob.description[:40],
                    "team": ob.owner_team,
                    "status": ob.status,
                }
            )

        edges = [
            {
                "source": f"team:{ob.owner_team}",
                "target": f"obligation:{ob.id}",
                "type": "owns",
            }
            for ob in obligations[:50]
        ]

        return {
            "teams": teams,
            "workflows_active": len(workflows),
            "exposure": exposure,
            "graph": {"nodes": nodes, "edges": edges},
            "simulation_ready": True,
        }

    def simulate_future(self, *, days: int = 30) -> dict:
        snap = self.snapshot()
        total_ob = sum(t["obligations"] for t in snap["teams"].values())
        overdue = sum(t["overdue"] for t in snap["teams"].values())
        pressure = snap["exposure"].get("regulatory_pressure_index", 0.5)

        projected_overdue = min(total_ob, overdue + int(days / 7 * pressure * 5))
        projected_load = {
            team: {
                "current": data["obligations"],
                "projected": data["obligations"] + int(days / 14),
            }
            for team, data in snap["teams"].items()
        }

        return {
            "horizon_days": days,
            "projected_overdue_obligations": projected_overdue,
            "projected_team_load": projected_load,
            "enforcement_probability": min(
                1.0, snap["exposure"].get("enforcement_probability", 0.3) + days * 0.01
            ),
            "narrative": (
                f"In {days} days without remediation, overdue obligations may rise to "
                f"~{projected_overdue} under current pressure index {pressure:.2f}."
            ),
        }
