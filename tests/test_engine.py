from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from customer_handoff.engine import bind_zendesk_user, build_plan, reconcile_provider_state
from customer_handoff.models import HandoffValidationError


def valid_dataset() -> dict:
    return {
        "schema_version": "1.0.0",
        "dataset_id": "sm-systems-hubspot-zendesk-customer-handoff-v1",
        "classification": "proof_safe_controlled_records",
        "records": [
            {
                "handoff_id": "SM-HZ-20260802-001",
                "company_name": "Northstar Facilities Group",
                "company_domain": "northstar.example.invalid",
                "contact_first_name": "Avery",
                "contact_last_name": "Hart",
                "contact_email": "avery.hart@example.invalid",
                "city": "Melbourne",
                "state": "VIC",
                "service_type": "Workflow Automation Retainer",
                "hubspot_stage": "won",
                "deal_id": "SM-HZ-DEAL-001",
                "deal_name": "Customer Operations Automation",
                "next_action": "Prepare the customer support workspace",
                "owner": "Stefan",
                "owner_approved": True,
                "proof_safe": True,
            }
        ],
    }


class EngineTests(unittest.TestCase):
    def write_dataset(self, value: dict) -> Path:
        temporary = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(value, temporary)
        temporary.close()
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_plan_maps_one_approved_won_relationship(self) -> None:
        plan = build_plan(self.write_dataset(valid_dataset()))
        self.assertEqual(plan["plan_id"], "SM-HZ-20260802-001")
        self.assertEqual(plan["hubspot_dataset"]["records"][0]["stage"], "won")
        organization = plan["zendesk_organization"]["organization"]
        self.assertEqual(organization["external_id"], "SM-HZ-20260802-001")
        self.assertNotIn("ai", " ".join(organization["tags"]))
        self.assertNotIn("jira", " ".join(organization["tags"]))
        user = bind_zendesk_user(plan, 123)["user"]
        self.assertEqual(user["organization_id"], 123)
        self.assertEqual(user["role"], "end-user")
        self.assertTrue(user["skip_verify_email"])

    def test_unapproved_record_is_rejected(self) -> None:
        dataset = valid_dataset()
        dataset["records"][0]["owner_approved"] = False
        with self.assertRaisesRegex(HandoffValidationError, "owner_approved"):
            build_plan(self.write_dataset(dataset))

    def test_non_won_deal_is_rejected(self) -> None:
        dataset = valid_dataset()
        dataset["records"][0]["hubspot_stage"] = "qualified"
        with self.assertRaisesRegex(HandoffValidationError, "won HubSpot deal"):
            build_plan(self.write_dataset(dataset))

    def test_provider_visible_test_label_is_rejected(self) -> None:
        dataset = valid_dataset()
        dataset["records"][0]["deal_name"] = "Synthetic proof deal"
        with self.assertRaisesRegex(HandoffValidationError, "blocked labels"):
            build_plan(self.write_dataset(dataset))

    def test_reconciliation_requires_exactly_one_organization_and_user(self) -> None:
        plan = build_plan(self.write_dataset(valid_dataset()))
        result = reconcile_provider_state(
            plan,
            {
                "results": [
                    {
                        "association_readback_available": True,
                        "associations": {
                            "company_contact": True,
                            "deal_company": True,
                            "deal_contact": True,
                        },
                        "company_found": True,
                        "company_stable_key": "companies.domain:northstar.example.invalid",
                        "contact_found": True,
                        "contact_stable_key": "contacts.email:avery.hart@example.invalid",
                        "deal_found": True,
                        "deal_name_collision": False,
                        "deal_stable_key": "deals.sm_systems_deal_id:SM-HZ-DEAL-001",
                    }
                ]
            },
            {"organization": {"id": 501, "external_id": "SM-HZ-20260802-001"}},
            {
                "user": {
                    "id": 601,
                    "external_id": "SM-HZ-20260802-001-USER",
                    "organization_id": 501,
                }
            },
        )
        self.assertEqual(result["state"], "reconciled")
        self.assertTrue(result["idempotency_passed"])

    def test_reconciliation_rejects_incomplete_hubspot_associations(self) -> None:
        plan = build_plan(self.write_dataset(valid_dataset()))
        result = reconcile_provider_state(
            plan,
            {
                "results": [
                    {
                        "association_readback_available": True,
                        "associations": {
                            "company_contact": True,
                            "deal_company": True,
                            "deal_contact": False,
                        },
                        "company_found": True,
                        "company_stable_key": "companies.domain:northstar.example.invalid",
                        "contact_found": True,
                        "contact_stable_key": "contacts.email:avery.hart@example.invalid",
                        "deal_found": True,
                        "deal_name_collision": False,
                        "deal_stable_key": "deals.sm_systems_deal_id:SM-HZ-DEAL-001",
                    }
                ]
            },
            {"organization": {"id": 501, "external_id": "SM-HZ-20260802-001"}},
            {
                "user": {
                    "id": 601,
                    "external_id": "SM-HZ-20260802-001-USER",
                    "organization_id": 501,
                }
            },
        )
        self.assertEqual(result["state"], "not_reconciled")
        self.assertFalse(result["hubspot_source_matched"])

    def test_reconciliation_rejects_duplicate_zendesk_organization(self) -> None:
        plan = build_plan(self.write_dataset(valid_dataset()))
        result = reconcile_provider_state(
            plan,
            {
                "results": [
                    {
                        "association_readback_available": True,
                        "associations": {
                            "company_contact": True,
                            "deal_company": True,
                            "deal_contact": True,
                        },
                        "company_found": True,
                        "company_stable_key": "companies.domain:northstar.example.invalid",
                        "contact_found": True,
                        "contact_stable_key": "contacts.email:avery.hart@example.invalid",
                        "deal_found": True,
                        "deal_name_collision": False,
                        "deal_stable_key": "deals.sm_systems_deal_id:SM-HZ-DEAL-001",
                    }
                ]
            },
            {
                "organizations": [
                    {"external_id": "SM-HZ-20260802-001"},
                    {"external_id": "SM-HZ-20260802-001"},
                ]
            },
            {
                "user": {
                    "external_id": "SM-HZ-20260802-001-USER",
                    "organization_id": 501,
                }
            },
        )
        self.assertEqual(result["state"], "not_reconciled")
        self.assertFalse(result["idempotency_passed"])


if __name__ == "__main__":
    unittest.main()
