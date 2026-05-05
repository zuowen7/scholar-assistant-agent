"""数据可用性声明 — 单元测试"""
from __future__ import annotations

import pytest
from src.formatter.data_availability import (
    AccessRoute,
    DatasetInfo,
    DataAvailabilityResult,
    generate_statement,
    format_data_availability_section,
)


class TestAccessRoute:
    def test_seven_routes(self) -> None:
        assert len(AccessRoute) == 7

    def test_public_repo_value(self) -> None:
        assert AccessRoute.PUBLIC_REPO.value == "public_repository"

    def test_controlled_access_value(self) -> None:
        assert AccessRoute.CONTROLLED_ACCESS.value == "controlled_access"

    def test_within_paper_value(self) -> None:
        assert AccessRoute.WITHIN_PAPER.value == "within_paper_or_supplement"

    def test_on_request_value(self) -> None:
        assert AccessRoute.ON_REQUEST.value == "available_on_request"

    def test_not_applicable_value(self) -> None:
        assert AccessRoute.NOT_APPLICABLE.value == "not_applicable"

    def test_string_coercion(self) -> None:
        assert AccessRoute("public_repository") == AccessRoute.PUBLIC_REPO


class TestDatasetInfo:
    def test_defaults(self) -> None:
        ds = DatasetInfo()
        assert ds.name == ""
        assert ds.access_route == AccessRoute.NOT_APPLICABLE
        assert ds.repository == ""
        assert ds.identifier == ""

    def test_full_construction(self) -> None:
        ds = DatasetInfo(
            name="RNA-seq data",
            access_route=AccessRoute.PUBLIC_REPO,
            repository="GEO",
            identifier="GSE12345",
            description="Transcriptome of treated cells",
            license_info="CC-BY 4.0",
        )
        assert ds.name == "RNA-seq data"
        assert ds.access_route == AccessRoute.PUBLIC_REPO
        assert ds.identifier == "GSE12345"

    def test_restriction_fields(self) -> None:
        ds = DatasetInfo(
            name="Patient data",
            access_route=AccessRoute.CONTROLLED_ACCESS,
            restriction_reason="Contains PHI",
            access_contact="ethics@university.edu",
        )
        assert ds.restriction_reason == "Contains PHI"
        assert ds.access_contact == "ethics@university.edu"


class TestGenerateStatement:
    def test_returns_data_availability_result(self) -> None:
        datasets = [
            DatasetInfo(name="RNA-seq data", access_route=AccessRoute.PUBLIC_REPO,
                       repository="GEO", identifier="GSE12345")
        ]
        result = generate_statement(datasets)
        assert isinstance(result, DataAvailabilityResult)

    def test_generates_statement_for_public_repo(self) -> None:
        datasets = [
            DatasetInfo(name="Sequencing data", access_route=AccessRoute.PUBLIC_REPO,
                       repository="SRA", identifier="PRJNA123456")
        ]
        result = generate_statement(datasets)
        assert len(result.statement) > 0

    def test_generates_on_request_statement(self) -> None:
        datasets = [
            DatasetInfo(name="Custom code", access_route=AccessRoute.ON_REQUEST,
                       access_contact="author@university.edu")
        ]
        result = generate_statement(datasets)
        assert len(result.statement) > 0
        assert "request" in result.statement.lower()

    def test_generates_not_applicable_statement(self) -> None:
        datasets = [
            DatasetInfo(name="Theoretical work", access_route=AccessRoute.NOT_APPLICABLE,
                       description="No datasets were generated")
        ]
        result = generate_statement(datasets)
        assert len(result.statement) > 0

    def test_computes_fair_score(self) -> None:
        datasets = [
            DatasetInfo(name="Public data", access_route=AccessRoute.PUBLIC_REPO,
                       repository="GEO", identifier="GSE12345", license_info="CC-BY 4.0")
        ]
        result = generate_statement(datasets)
        assert hasattr(result, 'fair_score')
        assert isinstance(result.fair_score, int)
        assert 0 <= result.fair_score <= 100

    def test_fair_score_lower_for_missing_fields(self) -> None:
        complete = generate_statement([
            DatasetInfo(name="Complete", access_route=AccessRoute.PUBLIC_REPO,
                       repository="GEO", identifier="GSE12345", license_info="CC-BY 4.0")
        ])
        minimal = generate_statement([
            DatasetInfo(name="Minimal", access_route=AccessRoute.ON_REQUEST)
        ])
        assert minimal.fair_score <= complete.fair_score

    def test_detects_missing_fields(self) -> None:
        datasets = [
            DatasetInfo(name="Incomplete", access_route=AccessRoute.PUBLIC_REPO)
            # missing identifier and repository
        ]
        result = generate_statement(datasets)
        assert hasattr(result, 'missing_fields')
        assert isinstance(result.missing_fields, list)

    def test_multiple_datasets(self) -> None:
        datasets = [
            DatasetInfo(name="Data A", access_route=AccessRoute.PUBLIC_REPO,
                       repository="GEO", identifier="GSE1"),
            DatasetInfo(name="Data B", access_route=AccessRoute.WITHIN_PAPER,
                       description="Supplementary Table 1"),
        ]
        result = generate_statement(datasets)
        assert len(result.statement) > 0

    def test_cn_checks_present(self) -> None:
        datasets = [
            DatasetInfo(name="测试数据", access_route=AccessRoute.PUBLIC_REPO,
                       repository="GEO", identifier="GSE12345"),
        ]
        result = generate_statement(datasets)
        assert hasattr(result, 'cn_checks')
        assert isinstance(result.cn_checks, list)


class TestFormatDataAvailabilitySection:
    def test_returns_markdown_with_datasets(self) -> None:
        datasets = [
            DatasetInfo(name="RNA-seq", access_route=AccessRoute.PUBLIC_REPO,
                       repository="GEO", identifier="GSE12345")
        ]
        result = format_data_availability_section(datasets=datasets)
        assert isinstance(result, str)
        assert "Data Availability" in result

    def test_returns_markdown_with_statement_text(self) -> None:
        result = format_data_availability_section(
            statement_text="All data are in the paper."
        )
        assert isinstance(result, str)
        assert "Data Availability" in result

    def test_handles_empty(self) -> None:
        result = format_data_availability_section()
        assert isinstance(result, str)
        assert "Data Availability" in result
