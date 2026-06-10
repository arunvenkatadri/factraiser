from factraiser.config import Guardrails
from factraiser.guardrails import check_for_scope, scan


def cats(findings):
    return {f.category for f in findings}


def test_detects_pii():
    g = Guardrails()
    text = "Reach Jane at jane.doe@example.com or 555-867-5309, SSN 123-45-6789."
    assert {"pii"} <= cats(scan(text, g))


def test_detects_secrets():
    g = Guardrails()
    text = "Use AKIAIOSFODNN7EXAMPLE and password=hunter2 for the legacy box."
    found = scan(text, g)
    labels = {f.label for f in found}
    assert "AWS access key" in labels
    assert "password assignment" in labels


def test_credit_card_requires_luhn():
    g = Guardrails()
    assert any(f.label == "credit card number" for f in scan("card: 4111 1111 1111 1111", g))
    assert not any(f.label == "credit card number" for f in scan("order id 1234 5678 9012 3456", g))


def test_detects_hr_and_legal():
    g = Guardrails()
    assert "hr" in cats(scan("Her salary review is pending termination decision.", g))
    assert "legal" in cats(scan("This is covered by attorney-client privilege in the lawsuit.", g))


def test_custom_blocklist():
    g = Guardrails(custom_blocklist=["project titan"])
    assert "custom" in cats(scan("Notes on Project Titan launch.", g))


def test_personal_scope_never_blocked():
    g = Guardrails()
    text = "my own ssn is 123-45-6789"
    assert check_for_scope(text, "personal", g) == []
    assert check_for_scope(text, "team", g)
    assert check_for_scope(text, "org", g)


def test_categories_can_be_disabled():
    g = Guardrails(blocked_categories=["pii"])
    assert scan("discussing salary bands", g) == []
