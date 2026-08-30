"""Offline integrity and production-consumption checks for Work F profiles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml
from jsonschema import Draft202012Validator


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parents[1]
VENUES = ["NeurIPS", "ICML", "ICLR", "ACL", "CVPR", "KDD", "CHI"]
EXPECTED_COUNTS = {
    "NeurIPS": 3,
    "ICML": 2,
    "ICLR": 2,
    "ACL": 3,
    "CVPR": 4,
    "KDD": 2,
    "CHI": 4,
}


def _json(name: str):
    return json.loads((BASE_DIR / "criteria" / name).read_text(encoding="utf-8"))


def _schema(name: str) -> dict:
    value = json.loads((BASE_DIR / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def _errors(instance, schema_name: str) -> list[str]:
    validator = Draft202012Validator(_schema(schema_name))
    return [error.message for error in validator.iter_errors(instance)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_official_sources_are_schema_valid_and_lineage_complete() -> None:
    records = _json("official_sources.json")
    assert not _errors(records, "official_sources.schema.json")
    assert [record["venue"] for record in records] == VENUES

    all_sources = [source for record in records for source in record["sources"]]
    assert len(all_sources) == 20
    assert len({source["source_id"] for source in all_sources}) == 20
    assert len({source["canonical_url"] for source in all_sources}) == 20
    assert {
        record["venue"]: len(record["sources"]) for record in records
    } == EXPECTED_COUNTS

    for record in records:
        packet = record["lineage"]["source_packet"]
        synthesis = record["lineage"]["synthesis_review"]
        assert packet["sha256"] == _sha256(REPO_ROOT / packet["path"])
        assert synthesis["sha256"] == _sha256(REPO_ROOT / synthesis["path"])
        for source in record["sources"]:
            assert source["venue"] == record["venue"]
            parsed = urlparse(source["canonical_url"])
            assert parsed.hostname == source["official_host"]
            assert source["source_packet"] == packet["path"]
            assert source["snapshot"] == {
                "status": "pending_g2",
                "path": None,
                "sha256": None,
            }


def test_criterion_map_is_schema_valid_and_matches_yaml_and_sources() -> None:
    records = _json("criterion_map.json")
    assert not _errors(records, "criterion_map.schema.json")
    assert [record["venue"] for record in records] == VENUES

    profiles = yaml.safe_load(
        (REPO_ROOT / "python/src/argument/venue_profiles.yaml").read_text(
            encoding="utf-8"
        )
    )
    source_records = _json("official_sources.json")
    source_by_id = {
        source["source_id"]: source
        for record in source_records
        for source in record["sources"]
    }
    criteria = [criterion for record in records for criterion in record["criteria"]]
    assert len(criteria) == 35
    assert len({criterion["criterion_id"] for criterion in criteria}) == 35

    for record in records:
        venue = record["venue"]
        expected_sentences = profiles[venue].splitlines()
        assert len(record["criteria"]) == len(expected_sentences)
        assert [criterion["rater_order"] for criterion in record["criteria"]] == list(
            range(1, len(expected_sentences) + 1)
        )
        for criterion, sentence in zip(record["criteria"], expected_sentences):
            assert criterion["profile_sentence"] == sentence
            assert criterion["rater_text"] == sentence
            assert (
                criterion["criterion_id"]
                == f"{venue.upper()}-C{criterion['rater_order']}"
            )
            assert criterion["profile_atom_id"].startswith(f"{venue.upper()}-Y")
            assert all(
                source_id in source_by_id for source_id in criterion["source_ids"]
            )
            assert all(
                source_by_id[source_id]["venue"] == venue
                for source_id in criterion["source_ids"]
            )
            assert (
                criterion["applicability"]["excerpt_insufficient_default"]
                == "applicable"
            )

    removed = [
        atom for record in records for atom in record["removed_profile_atom_ids"]
    ]
    assert sorted(removed) == sorted(
        ["ICML-Y4", "ICLR-Y1", "ICLR-Y2", "ICLR-Y4", "ACL-Y3", "CVPR-Y2", "CVPR-Y4"]
    )


def test_chi_y4_source_order_matches_synthesis_replacement_and_criterion_map() -> None:
    synthesis = (BASE_DIR / "sources" / "synthesis_review.md").read_text(
        encoding="utf-8"
    )
    assert (
        "| CHI-Y4 | ethical considerations for human subjects | keep | CHI-S4; CHI-S2 |"
        in synthesis
    )
    assert "5. **CHI-Y4**" in synthesis
    assert "*(CHI-S4; CHI-S2)*" in synthesis

    chi = next(
        record for record in _json("criterion_map.json") if record["venue"] == "CHI"
    )
    chi_y4 = next(
        criterion
        for criterion in chi["criteria"]
        if criterion["profile_atom_id"] == "CHI-Y4"
    )
    assert chi_y4["source_ids"] == ["CHI-S4", "CHI-S2"]


def test_profile_schema_rejects_unknown_fields_and_invalid_snapshots() -> None:
    sources = _json("official_sources.json")
    with_extra = json.loads(json.dumps(sources))
    with_extra[0]["sources"][0]["unexpected"] = True
    assert _errors(with_extra, "official_sources.schema.json")

    bad_snapshot = json.loads(json.dumps(sources))
    bad_snapshot[0]["sources"][0]["snapshot"] = {
        "status": "pending_g2",
        "path": "snapshots/source.html",
        "sha256": "0" * 64,
    }
    assert _errors(bad_snapshot, "official_sources.schema.json")

    criteria = _json("criterion_map.json")
    bad_criterion = json.loads(json.dumps(criteria))
    bad_criterion[0]["criteria"][0]["source_ids"] = []
    assert _errors(bad_criterion, "criterion_map.schema.json")


def test_generic_control_is_byte_exact_and_claims_are_hygienic() -> None:
    profile_path = REPO_ROOT / "python/src/argument/venue_profiles.yaml"
    raw = profile_path.read_bytes()
    start = raw.index(b"generic: |")
    end = raw.index(b"\nNeurIPS: |") + 1
    generic_block = raw[start:end]
    assert len(generic_block) == 219
    assert (
        hashlib.sha256(generic_block).hexdigest()
        == "30fd129da348e52128cfceab4844b54dedb7abdb39c9fe217251bc29fb60619a"
    )

    active = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in (
            "README.md",
            "README_zh.md",
            "python/src/argument/reviewer.py",
            "python/src/argument/venue_profiles.yaml",
        )
    ).lower()
    for phrase in (
        "conference-calibrated",
        "calibrated reviews",
        "会议校准",
        "venue calibration profiles",
        "calibration text",
        "review culture and hard requirements",
        "generalisation claims backed by multiple datasets",
        "open-source code (expected, not optional)",
        "ablation completeness",
        "addressing reviewer comments from prior submissions if applicable",
        "human evaluation where automatic metrics are insufficient",
        "ablation study isolating visual components",
        "comparison on standard benchmarks (imagenet, coco, etc.)",
    ):
        assert phrase not in active

    criterion_text = json.dumps(_json("criterion_map.json"), ensure_ascii=False).lower()
    for phrase in (
        "generalisation claims backed by multiple datasets",
        "open-source code (expected, not optional)",
        "ablation completeness",
        "addressing reviewer comments from prior submissions if applicable",
        "human evaluation where automatic metrics are insufficient",
        "ablation study isolating visual components",
        "comparison on standard benchmarks (imagenet, coco, etc.)",
    ):
        assert phrase not in criterion_text


@pytest.mark.asyncio
@pytest.mark.parametrize("venue", VENUES)
@pytest.mark.parametrize("focused", [False, True])
async def test_production_prompts_consume_complete_profile(
    tmp_path: Path, venue: str, focused: bool
) -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "python"))
    from src.argument.reviewer import _load_venue_profile, run_review
    from src.argument.companion_store import CompanionStore

    profile = _load_venue_profile(venue)
    first, *_, last = profile.splitlines()
    prompts: list[str] = []

    async def capture_prompt(prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return "[]"

    kwargs = {"focus": {"quote": "A short excerpt"}} if focused else {}
    async for _event in run_review(
        doc_id="grounding-doc",
        text="A short excerpt for a deterministic mock review.",
        venue=venue,
        checks=["llm"],
        store=CompanionStore(runtime_dir=tmp_path),
        cloud_client=object(),
        llm_call=capture_prompt,
        raise_llm_errors=True,
        **kwargs,
    ):
        pass

    assert len(prompts) == 1
    assert profile in prompts[0]
    assert first in prompts[0]
    assert last in prompts[0]
