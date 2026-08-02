from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class HandoffValidationError(ValueError):
    """Raised when a handoff record violates the approved contract."""


@dataclass(frozen=True)
class HandoffRecord:
    handoff_id: str
    company_name: str
    company_domain: str
    contact_first_name: str
    contact_last_name: str
    contact_email: str
    city: str
    state: str
    service_type: str
    hubspot_stage: str
    deal_id: str
    deal_name: str
    next_action: str
    owner: str
    owner_approved: bool
    proof_safe: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HandoffRecord":
        required = {
            "handoff_id",
            "company_name",
            "company_domain",
            "contact_first_name",
            "contact_last_name",
            "contact_email",
            "city",
            "state",
            "service_type",
            "hubspot_stage",
            "deal_id",
            "deal_name",
            "next_action",
            "owner",
            "owner_approved",
            "proof_safe",
        }
        missing = sorted(required.difference(data))
        if missing:
            raise HandoffValidationError(
                f"record is missing required fields: {', '.join(missing)}"
            )
        record = cls(**{key: data[key] for key in required})
        record.validate()
        return record

    def validate(self) -> None:
        text_fields = {
            "handoff_id": self.handoff_id,
            "company_name": self.company_name,
            "company_domain": self.company_domain,
            "contact_first_name": self.contact_first_name,
            "contact_last_name": self.contact_last_name,
            "contact_email": self.contact_email,
            "city": self.city,
            "state": self.state,
            "service_type": self.service_type,
            "hubspot_stage": self.hubspot_stage,
            "deal_id": self.deal_id,
            "deal_name": self.deal_name,
            "next_action": self.next_action,
            "owner": self.owner,
        }
        empty = sorted(name for name, value in text_fields.items() if not value.strip())
        if empty:
            raise HandoffValidationError(
                f"record has empty required fields: {', '.join(empty)}"
            )
        if not self.owner_approved:
            raise HandoffValidationError("owner_approved must be true")
        if not self.proof_safe:
            raise HandoffValidationError("proof_safe must be true")
        if self.hubspot_stage != "won":
            raise HandoffValidationError("only a won HubSpot deal may enter this handoff")
        if "@" not in self.contact_email or self.contact_email.startswith("@"):
            raise HandoffValidationError("contact_email must be valid")
