from __future__ import annotations

import json
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED = {
    "README.md",
    "LICENSE",
    "Makefile",
    "pyproject.toml",
    "examples/controlled-handoff.json",
    "docs/architecture.md",
    "docs/case-study.md",
    "docs/runbook.md",
    "src/customer_handoff/cli.py",
    "src/customer_handoff/engine.py",
    "src/customer_handoff/models.py",
}
FORBIDDEN_TEXT = {
    "/Users/",
    "@smsystems.au",
    "stefan+hubspot",
    "279567282656",
    "284503250363",
    "342483312078",
}


def png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"not a PNG: {path}")
    return struct.unpack(">II", payload[16:24])


def main() -> None:
    missing = sorted(path for path in REQUIRED if not (ROOT / path).exists())
    if missing:
        raise AssertionError(f"missing public files: {missing}")

    proof = sorted((ROOT / "proof").glob("*.png"))
    if len(proof) != 5:
        raise AssertionError("public proof package must contain exactly five PNGs")
    for path in proof:
        if png_dimensions(path) != (1280, 960):
            raise AssertionError(f"unexpected proof dimensions: {path.name}")

    findings: dict[str, list[str]] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".pyc"}:
            continue
        if path.name == "validate_public.py":
            continue
        text = path.read_text(encoding="utf-8")
        hits = sorted(term for term in FORBIDDEN_TEXT if term in text)
        if hits:
            findings[str(path.relative_to(ROOT))] = hits
    if findings:
        raise AssertionError(f"private content found: {findings}")

    dataset = json.loads(
        (ROOT / "examples/controlled-handoff.json").read_text(encoding="utf-8")
    )
    if len(dataset.get("records", [])) != 1:
        raise AssertionError("example must contain exactly one controlled record")

    print(
        json.dumps(
            {
                "state": "validation_passed",
                "proof_image_count": len(proof),
                "proof_dimensions": "1280x960",
                "private_text_findings": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
