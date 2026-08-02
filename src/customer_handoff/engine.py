from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import HandoffRecord, HandoffValidationError


SCHEMA_VERSION = "1.0.0"
BLOCKED_VISIBLE_TERMS = (
    "fixture",
    "synthetic",
    "sandbox",
    "proof",
    "demo",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_dataset(path: Path) -> tuple[dict[str, Any], HandoffRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise HandoffValidationError("unsupported dataset schema_version")
    records = data.get("records")
    if not isinstance(records, list) or len(records) != 1:
        raise HandoffValidationError("dataset must contain exactly one record")
    record = HandoffRecord.from_dict(records[0])
    _validate_provider_visible_labels(record)
    return data, record


def _validate_provider_visible_labels(record: HandoffRecord) -> None:
    visible = " ".join(
        [record.company_name, record.deal_name, record.service_type, record.next_action]
    ).lower()
    found = [term for term in BLOCKED_VISIBLE_TERMS if term in visible]
    if found:
        raise HandoffValidationError(
            "provider-visible values contain blocked labels: " + ", ".join(found)
        )


def build_hubspot_dataset(record: HandoffRecord) -> dict[str, Any]:
    return {
        "dataset_id": "sm-systems-hubspot-zendesk-customer-handoff-v1",
        "version": "1.0.0",
        "classification": "proof_safe_controlled_records",
        "records": [
            {
                "lead_id": "HZ-L001",
                "case_id": record.handoff_id,
                "first_name": record.contact_first_name,
                "last_name": record.contact_last_name,
                "email": record.contact_email,
                "phone": "",
                "street_address": "",
                "city": record.city,
                "state": record.state,
                "postal_code": "",
                "service_type": record.service_type,
                "owner": record.owner,
                "stage": record.hubspot_stage,
                "company_id": "HZ-CO001",
                "company_name": record.company_name,
                "company_domain": record.company_domain,
                "deal_id": record.deal_id,
                "deal_name": record.deal_name,
                "source": "owner_approved_customer_handoff",
                "source_ref": record.handoff_id,
                "owner_approved": record.owner_approved,
                "proof_safe": record.proof_safe,
                "next_action": record.next_action,
            }
        ],
        "negative_cases": [
            {
                "case_id": "HZ-N001",
                "type": "duplicate_handoff_id",
                "input_ref": record.handoff_id,
                "expected": "match_existing_without_duplicate_provider_objects",
            },
            {
                "case_id": "HZ-N002",
                "type": "owner_approved_false",
                "expected": "blocked_before_provider_write",
            },
            {
                "case_id": "HZ-N003",
                "type": "deal_stage_not_won",
                "expected": "blocked_before_provider_write",
            },
        ],
    }


def build_zendesk_organization(record: HandoffRecord) -> dict[str, Any]:
    return {
        "organization": {
            "name": record.company_name,
            "external_id": record.handoff_id,
            "tags": [
                "sm_crm_handoff",
                "hubspot_customer_context",
                "workflow_automation",
            ],
            "details": f"Service: {record.service_type}",
            "notes": (
                f"HubSpot deal: {record.deal_name}. "
                f"Next action: {record.next_action}."
            ),
        }
    }


def build_zendesk_user_template(record: HandoffRecord) -> dict[str, Any]:
    return {
        "name": f"{record.contact_first_name} {record.contact_last_name}",
        "email": record.contact_email,
        "external_id": f"{record.handoff_id}-USER",
        "role": "end-user",
        "verified": False,
        "skip_verify_email": True,
        "tags": ["sm_crm_handoff", "hubspot_customer_context"],
    }


def bind_zendesk_user(plan: dict[str, Any], organization_id: int) -> dict[str, Any]:
    if organization_id < 1:
        raise HandoffValidationError("organization_id must be positive")
    template = dict(plan["zendesk_user_template"])
    template["organization_id"] = organization_id
    return {"user": template}


def build_plan(dataset_path: Path) -> dict[str, Any]:
    source, record = load_dataset(dataset_path)
    hubspot = build_hubspot_dataset(record)
    zendesk_organization = build_zendesk_organization(record)
    zendesk_user_template = build_zendesk_user_template(record)
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": record.handoff_id,
        "state": "local_plan_complete_provider_execution_blocked_pending_exact_approval",
        "source_dataset_sha256": sha256_json(source),
        "hubspot_dataset": hubspot,
        "hubspot_dataset_sha256": sha256_json(hubspot),
        "zendesk_organization": zendesk_organization,
        "zendesk_organization_payload_sha256": sha256_json(zendesk_organization),
        "zendesk_user_template": zendesk_user_template,
        "zendesk_user_template_sha256": sha256_json(zendesk_user_template),
        "provider_sequence": [
            "hubspot_plan",
            "hubspot_exact_approval",
            "hubspot_fill",
            "hubspot_readback",
            "zendesk_organization_dry_run",
            "zendesk_organization_exact_approval",
            "zendesk_organization_upsert",
            "zendesk_organization_readback",
            "bind_zendesk_organization_id",
            "zendesk_user_dry_run",
            "zendesk_user_exact_approval",
            "zendesk_user_upsert",
            "zendesk_user_readback",
            "cross_provider_reconciliation",
        ],
        "blocked_actions": [
            "public_zendesk_comment",
            "email_or_sms",
            "workflow_activation",
            "ai_generation",
            "jira_escalation",
            "github_or_website_publication",
        ],
    }


def reconcile_provider_state(
    plan: dict[str, Any],
    hubspot_readback: dict[str, Any],
    zendesk_organization_readback: dict[str, Any],
    zendesk_user_readback: dict[str, Any],
) -> dict[str, Any]:
    expected = plan["plan_id"]
    hubspot_match = _hubspot_source_matched(plan, hubspot_readback)
    organization_count = _count_external_id(zendesk_organization_readback, expected)
    user_count = _count_external_id(zendesk_user_readback, f"{expected}-USER")
    organization_id = _find_provider_id(zendesk_organization_readback, expected)
    user_organization_id = _find_user_organization_id(
        zendesk_user_readback, f"{expected}-USER"
    )
    relationship_match = (
        organization_id is not None and user_organization_id == organization_id
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": expected,
        "hubspot_source_matched": hubspot_match,
        "zendesk_organization_match_count": organization_count,
        "zendesk_user_match_count": user_count,
        "zendesk_user_organization_matched": relationship_match,
        "idempotency_passed": organization_count == 1 and user_count == 1,
        "state": (
            "reconciled"
            if hubspot_match
            and organization_count == 1
            and user_count == 1
            and relationship_match
            else "not_reconciled"
        ),
        "provider_mutation_inferred": False,
    }


def _hubspot_source_matched(
    plan: dict[str, Any], hubspot_readback: dict[str, Any]
) -> bool:
    planned_record = plan["hubspot_dataset"]["records"][0]
    expected_keys = {
        "company_stable_key": (
            f"companies.domain:{planned_record['company_domain']}"
        ),
        "contact_stable_key": f"contacts.email:{planned_record['email']}",
        "deal_stable_key": f"deals.sm_systems_deal_id:{planned_record['deal_id']}",
    }
    results = hubspot_readback.get("results")
    if not isinstance(results, list) or len(results) != 1:
        return False
    result = results[0]
    if not isinstance(result, dict):
        return False
    associations = result.get("associations")
    return (
        result.get("company_found") is True
        and result.get("contact_found") is True
        and result.get("deal_found") is True
        and result.get("deal_name_collision") is False
        and result.get("association_readback_available") is True
        and associations
        == {
            "company_contact": True,
            "deal_company": True,
            "deal_contact": True,
        }
        and all(result.get(field) == value for field, value in expected_keys.items())
    )


def _count_external_id(value: Any, expected: str) -> int:
    if isinstance(value, dict):
        count = 1 if value.get("external_id") == expected else 0
        return count + sum(_count_external_id(item, expected) for item in value.values())
    if isinstance(value, list):
        return sum(_count_external_id(item, expected) for item in value)
    return 0


def _find_provider_id(value: Any, external_id: str) -> int | None:
    if isinstance(value, dict):
        if value.get("external_id") == external_id and isinstance(value.get("id"), int):
            return value["id"]
        for item in value.values():
            found = _find_provider_id(item, external_id)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_provider_id(item, external_id)
            if found is not None:
                return found
    return None


def _find_user_organization_id(value: Any, external_id: str) -> int | None:
    if isinstance(value, dict):
        if value.get("external_id") == external_id:
            organization_id = value.get("organization_id")
            return organization_id if isinstance(organization_id, int) else None
        for item in value.values():
            found = _find_user_organization_id(item, external_id)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_user_organization_id(item, external_id)
            if found is not None:
                return found
    return None
