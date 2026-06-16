"""Regulatory knowledge graph — entities and relationships."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.regulatory_entity import RegulatoryEntity
from app.models.regulatory_relationship import RegulatoryRelationship
from app.schemas.analysis import RegulatoryAnalysisOutput


class KnowledgeGraphService:
  def __init__(self, db: Session) -> None:
    self._db = db

  def upsert_regulation_node(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    title: str,
    summary: str,
    devrev_work_id: str | None = None,
  ) -> RegulatoryEntity:
    key = f"{regulator_code}:notification:{notification_id}"
    existing = (
      self._db.query(RegulatoryEntity)
      .filter(RegulatoryEntity.external_key == key)
      .first()
    )
    if existing:
      if devrev_work_id:
        existing.devrev_work_id = devrev_work_id
      self._db.commit()
      return existing

    entity = RegulatoryEntity(
      entity_type="regulation",
      regulator_code=regulator_code,
      external_key=key,
      title=title[:512],
      summary=summary[:4000] if summary else None,
      notification_id=notification_id,
      devrev_work_id=devrev_work_id,
    )
    self._db.add(entity)
    self._db.commit()
    self._db.refresh(entity)
    return entity

  def link_related(
    self,
    source: RegulatoryEntity,
    related_notification_ids: list[int],
    *,
    relationship_type: str = "similar_to",
  ) -> list[int]:
    created = []
    for nid in related_notification_ids:
      target_key = f"{source.regulator_code}:notification:{nid}"
      target = (
        self._db.query(RegulatoryEntity)
        .filter(RegulatoryEntity.external_key == target_key)
        .first()
      )
      if not target:
        continue
      rel = RegulatoryRelationship(
        source_entity_id=source.id,
        target_entity_id=target.id,
        relationship_type=relationship_type,
        strength=0.75,
        evidence="historical_correlation",
      )
      self._db.add(rel)
      created.append(rel.id)
    self._db.commit()
    return created

  def link_team_obligation(
    self,
    regulation_entity_id: int,
    team: str,
    obligation_entity_id: int,
  ) -> None:
    team_key = f"team:{team.lower().replace(' ', '_')}"
    team_entity = (
      self._db.query(RegulatoryEntity)
      .filter(RegulatoryEntity.external_key == team_key)
      .first()
    )
    if not team_entity:
      team_entity = RegulatoryEntity(
        entity_type="team",
        regulator_code="INTERNAL",
        external_key=team_key,
        title=team,
      )
      self._db.add(team_entity)
      self._db.commit()
      self._db.refresh(team_entity)

    for src, tgt, rtype in (
      (regulation_entity_id, team_entity.id, "assigned_to"),
      (obligation_entity_id, team_entity.id, "owned_by"),
      (regulation_entity_id, obligation_entity_id, "imposes"),
    ):
      self._db.add(
        RegulatoryRelationship(
          source_entity_id=src,
          target_entity_id=tgt,
          relationship_type=rtype,
          strength=1.0,
        )
      )
    self._db.commit()

  def subgraph_for_notification(self, notification_id: int) -> dict:
    key = f"%:notification:{notification_id}"
    root = (
      self._db.query(RegulatoryEntity)
      .filter(RegulatoryEntity.external_key.like(key))
      .first()
    )
    if not root:
      return {"nodes": [], "edges": []}

    edges = (
      self._db.query(RegulatoryRelationship)
      .filter(
        (RegulatoryRelationship.source_entity_id == root.id)
        | (RegulatoryRelationship.target_entity_id == root.id)
      )
      .all()
    )
    node_ids = {root.id}
    for e in edges:
      node_ids.add(e.source_entity_id)
      node_ids.add(e.target_entity_id)

    nodes = (
      self._db.query(RegulatoryEntity)
      .filter(RegulatoryEntity.id.in_(node_ids))
      .all()
    )
    return {
      "nodes": [
        {
          "id": n.id,
          "type": n.entity_type,
          "title": n.title,
          "regulator": n.regulator_code,
        }
        for n in nodes
      ],
      "edges": [
        {
          "source": e.source_entity_id,
          "target": e.target_entity_id,
          "type": e.relationship_type,
          "strength": e.strength,
        }
        for e in edges
      ],
    }

  def build_from_analysis(
    self,
    *,
    notification_id: int,
    regulator_code: str,
    title: str,
    analysis: RegulatoryAnalysisOutput,
    devrev_work_id: str | None,
    related_ids: list[int],
    obligation_ids: list[int],
  ) -> dict:
    reg_node = self.upsert_regulation_node(
      notification_id=notification_id,
      regulator_code=regulator_code,
      title=title,
      summary=analysis.executive_summary,
      devrev_work_id=devrev_work_id,
    )
    rel_ids = self.link_related(reg_node, related_ids)

    for oid in obligation_ids:
      ob_key = f"obligation:{oid}"
      ob_entity = RegulatoryEntity(
        entity_type="obligation",
        regulator_code=regulator_code,
        external_key=ob_key,
        title=f"Obligation #{oid}",
        notification_id=notification_id,
        metadata_json=json.dumps({"obligation_id": oid}),
      )
      self._db.add(ob_entity)
      self._db.commit()
      self._db.refresh(ob_entity)
      self.link_team_obligation(reg_node.id, analysis.suggested_owner_team, ob_entity.id)

    return {
      "regulation_entity_id": reg_node.id,
      "relationship_ids": rel_ids,
    }
