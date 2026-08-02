from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .engine import bind_zendesk_user, build_plan, reconcile_provider_state


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def command_plan(args: argparse.Namespace) -> int:
    dataset_path = Path(args.dataset).resolve()
    output_root = Path(args.output_root).resolve()
    plan = build_plan(dataset_path)
    write_json(output_root / "handoff-plan.json", plan)
    write_json(output_root / "hubspot-canonical-dataset.json", plan["hubspot_dataset"])
    write_json(
        output_root / "zendesk-organization-upsert.json",
        plan["zendesk_organization"],
    )
    write_json(
        output_root / "zendesk-user-unbound-template.json",
        plan["zendesk_user_template"],
    )
    write_json(
        output_root / "hubspot-stage-map.json",
        {"pipeline_id": "default", "stages": {"won": "closedwon"}},
    )
    print(json.dumps({"state": plan["state"], "plan_id": plan["plan_id"]}))
    return 0


def command_bind_user(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    organization = json.loads(
        Path(args.organization_readback).read_text(encoding="utf-8")
    )
    expected = plan["plan_id"]
    organization_id = _find_external_id(organization, expected)
    if organization_id is None:
        raise ValueError("organization readback did not contain the planned external ID")
    payload = bind_zendesk_user(plan, organization_id)
    write_json(Path(args.output).resolve(), payload)
    print(json.dumps({"state": "zendesk_user_payload_bound", "organization_id": organization_id}))
    return 0


def _find_external_id(value: Any, expected: str) -> int | None:
    if isinstance(value, dict):
        if value.get("external_id") == expected and isinstance(value.get("id"), int):
            return value["id"]
        for item in value.values():
            found = _find_external_id(item, expected)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_external_id(item, expected)
            if found is not None:
                return found
    return None


def command_reconcile(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    hubspot = json.loads(Path(args.hubspot_readback).read_text(encoding="utf-8"))
    organization = json.loads(
        Path(args.zendesk_organization_readback).read_text(encoding="utf-8")
    )
    user = json.loads(Path(args.zendesk_user_readback).read_text(encoding="utf-8"))
    result = reconcile_provider_state(plan, hubspot, organization, user)
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result))
    return 0 if result["state"] == "reconciled" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    plan = subcommands.add_parser("plan", help="Generate deterministic provider manifests")
    plan.add_argument("--dataset", required=True)
    plan.add_argument("--output-root", required=True)
    plan.set_defaults(handler=command_plan)

    bind_user = subcommands.add_parser(
        "bind-user", help="Bind the read-back Zendesk organization ID into the user payload"
    )
    bind_user.add_argument("--plan", required=True)
    bind_user.add_argument("--organization-readback", required=True)
    bind_user.add_argument("--output", required=True)
    bind_user.set_defaults(handler=command_bind_user)

    reconcile = subcommands.add_parser(
        "reconcile", help="Correlate HubSpot and Zendesk provider readbacks"
    )
    reconcile.add_argument("--plan", required=True)
    reconcile.add_argument("--hubspot-readback", required=True)
    reconcile.add_argument("--zendesk-organization-readback", required=True)
    reconcile.add_argument("--zendesk-user-readback", required=True)
    reconcile.add_argument("--output", required=True)
    reconcile.set_defaults(handler=command_reconcile)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
