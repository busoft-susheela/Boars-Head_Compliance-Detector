"""ComplianceRuleRepository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.models.compliance import ComplianceRule
from backend.app.infrastructure.database.repositories.base import BaseRepository


class ComplianceRuleRepository(BaseRepository[ComplianceRule]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ComplianceRule)

    def get_by_key(self, rule_key: str) -> ComplianceRule | None:
        return (
            self._session.query(ComplianceRule)
            .filter(ComplianceRule.rule_key == rule_key)
            .first()
        )

    def get_or_create(self, rule_key: str, name: str, use_case: str, configuration: dict | None = None) -> ComplianceRule:
        rule = self.get_by_key(rule_key)
        if rule is None:
            rule = ComplianceRule(
                rule_key=rule_key,
                name=name,
                use_case=use_case,
                configuration=configuration,
            )
            self.save(rule)
        return rule
