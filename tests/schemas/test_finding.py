"""Tests for schemas/finding.py - Complete coverage"""
import pytest
from pydantic import ValidationError

from schemas.finding import Evidence, Finding


class TestEvidence:
    """Tests for Evidence model."""

    def test_evidence_code_span(self):
        """Test creating code span evidence."""
        evidence = Evidence(
            type="code_span",
            file="test.py",
            start=10,
            end=15,
            sha="abc123"
        )
        assert evidence.type == "code_span"
        assert evidence.file == "test.py"
        assert evidence.start == 10
        assert evidence.end == 15

    def test_evidence_tool_output(self):
        """Test creating tool output evidence."""
        evidence = Evidence(
            type="tool_output",
            tool_id="lint",
            issue_id="E501",
            message="Line too long"
        )
        assert evidence.type == "tool_output"
        assert evidence.tool_id == "lint"

    def test_evidence_policy_quote(self):
        """Test creating policy quote evidence."""
        evidence = Evidence(
            type="policy_quote",
            doc_id="pep8",
            text="Lines should be <= 79 characters"
        )
        assert evidence.type == "policy_quote"
        assert evidence.text is not None

    def test_evidence_optional_fields(self):
        """Test evidence with only required fields."""
        evidence = Evidence(type="code_span")
        assert evidence.file is None
        assert evidence.start is None


class TestFinding:
    """Tests for Finding model."""

    def test_finding_complete(self):
        """Test creating complete finding."""
        finding = Finding(
            title="Line too long",
            severity="medium",
            file="test.py",
            line_start=10,
            line_end=10,
            category="style",
            description="Line exceeds 79 characters",
            evidence=[
                Evidence(type="code_span", file="test.py", start=10, end=10)
            ]
        )
        assert finding.title == "Line too long"
        assert finding.severity == "medium"
        assert len(finding.evidence) >= 1

    def test_finding_with_patch(self):
        """Test finding with suggested patch."""
        finding = Finding(
            title="Fix import",
            severity="low",
            file="test.py",
            line_start=1,
            line_end=1,
            category="style",
            description="Import not used",
            suggested_patch="- import unused\n",
            evidence=[Evidence(type="tool_output", tool_id="lint")]
        )
        assert finding.suggested_patch is not None

    def test_finding_with_references(self):
        """Test finding with references."""
        finding = Finding(
            title="Security issue",
            severity="high",
            file="app.py",
            line_start=50,
            line_end=52,
            category="security",
            description="SQL injection risk",
            evidence=[Evidence(type="tool_output", tool_id="security")],
            references=["https://owasp.org/sql-injection"]
        )
        assert len(finding.references) == 1

    def test_finding_severity_validation(self):
        """Test finding severity must be valid."""
        with pytest.raises(ValidationError):
            Finding(
                title="Test",
                severity="invalid",  # Invalid severity
                file="test.py",
                line_start=1,
                line_end=1,
                category="style",
                description="Test",
                evidence=[Evidence(type="code_span")]
            )

    def test_finding_category_validation(self):
        """Test finding category must be valid."""
        with pytest.raises(ValidationError):
            Finding(
                title="Test",
                severity="medium",
                file="test.py",
                line_start=1,
                line_end=1,
                category="invalid",  # Invalid category
                description="Test",
                evidence=[Evidence(type="code_span")]
            )

    def test_finding_requires_evidence(self):
        """Test finding requires at least one evidence."""
        with pytest.raises(ValidationError):
            Finding(
                title="Test",
                severity="medium",
                file="test.py",
                line_start=1,
                line_end=1,
                category="style",
                description="Test",
                evidence=[]  # Empty evidence
            )

    def test_finding_all_severities(self):
        """Test all valid severity levels."""
        severities = ["blocker", "high", "medium", "low", "nit"]
        for severity in severities:
            finding = Finding(
                title="Test",
                severity=severity,
                file="test.py",
                line_start=1,
                line_end=1,
                category="style",
                description="Test",
                evidence=[Evidence(type="code_span")]
            )
            assert finding.severity == severity

    def test_finding_all_categories(self):
        """Test all valid categories."""
        categories = ["security", "correctness", "performance", "style", "docs", "tests"]
        for category in categories:
            finding = Finding(
                title="Test",
                severity="medium",
                file="test.py",
                line_start=1,
                line_end=1,
                category=category,
                description="Test",
                evidence=[Evidence(type="code_span")]
            )
            assert finding.category == category
