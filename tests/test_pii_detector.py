"""
Tests for PII Detection and Redaction

Tests comprehensive PII detection across multiple data types.
"""

import pytest
from src.security.pii_detector import PIIDetector


@pytest.fixture
def detector():
    """Create a PII detector with default settings"""
    return PIIDetector(enabled=True, threshold=0.75)


class TestEmailDetection:
    """Test email address detection"""

    def test_simple_email(self, detector):
        text = "Contact me at john.doe@example.com for more info"
        result = detector.detect(text)
        assert result.pii_detected
        assert "email" in result.pii_types_found
        assert result.total_count == 1

    def test_multiple_emails(self, detector):
        text = "Email alice@test.com or bob@company.org"
        result = detector.detect(text)
        assert result.total_count == 2
        assert all(m.pii_type == "email" for m in result.matches)

    def test_email_with_numbers(self, detector):
        text = "user123@domain456.com"
        result = detector.detect(text)
        assert result.pii_detected
        assert "email" in result.pii_types_found

    def test_email_with_subdomain(self, detector):
        text = "admin@mail.company.co.uk"
        result = detector.detect(text)
        assert result.pii_detected

    def test_not_email(self, detector):
        text = "This is not an @ email address"
        result = detector.detect(text)
        assert not result.pii_detected

    def test_email_with_plus(self, detector):
        text = "user+tag@example.com"
        result = detector.detect(text)
        assert result.pii_detected


class TestPhoneDetection:
    """Test phone number detection"""

    def test_phone_with_parens(self, detector):
        text = "Call me at (555) 123-4567"
        result = detector.detect(text)
        assert result.pii_detected
        assert "phone" in result.pii_types_found

    def test_phone_with_dashes(self, detector):
        text = "My number: 555-123-4567"
        result = detector.detect(text)
        assert result.pii_detected

    def test_phone_with_dots(self, detector):
        text = "555.123.4567"
        result = detector.detect(text)
        assert result.pii_detected

    def test_phone_no_separators(self, detector):
        text = "5551234567"
        result = detector.detect(text)
        assert result.pii_detected

    def test_international_format(self, detector):
        text = "+1-555-123-4567"
        result = detector.detect(text)
        assert result.pii_detected

    def test_multiple_phones(self, detector):
        text = "Home: (555) 123-4567, Work: 555-987-6543"
        result = detector.detect(text)
        assert result.total_count == 2


class TestSSNDetection:
    """Test Social Security Number detection"""

    def test_ssn_with_dashes(self, detector):
        text = "SSN: 123-45-6789"
        result = detector.detect(text)
        assert result.pii_detected
        assert "ssn" in result.pii_types_found

    def test_ssn_with_spaces(self, detector):
        text = "123 45 6789"
        result = detector.detect(text)
        assert result.pii_detected

    def test_invalid_ssn_prefix(self, detector):
        # SSNs starting with 000, 666, or 900-999 are invalid
        text = "000-45-6789"
        result = detector.detect(text)
        # Should not match invalid SSN
        if result.pii_detected:
            assert "ssn" not in result.pii_types_found


class TestCreditCardDetection:
    """Test credit card number detection"""

    def test_visa_card(self, detector):
        # Valid Visa test card (passes Luhn check)
        text = "Card: 4532015112830366"
        result = detector.detect(text)
        assert result.pii_detected
        assert "credit_card" in result.pii_types_found

    def test_mastercard(self, detector):
        # Valid Mastercard test card
        text = "5425233430109903"
        result = detector.detect(text)
        assert result.pii_detected

    def test_amex(self, detector):
        # Valid Amex test card (15 digits)
        text = "374245455400126"
        result = detector.detect(text)
        assert result.pii_detected

    def test_invalid_luhn(self, detector):
        # Looks like a credit card but fails Luhn check
        text = "4532015112830367"  # Last digit changed
        result = detector.detect(text)
        # Should not match (Luhn validation fails)
        if result.pii_detected:
            assert "credit_card" not in result.pii_types_found


class TestAPIKeyDetection:
    """Test API key and secret detection"""

    def test_api_key_pattern(self, detector):
        text = "api_key: test_key_abcdefghijklmnopqrstuvwxyz"
        result = detector.detect(text)
        # API key detection has lower confidence (0.75)
        # Should match with default threshold
        assert result.pii_detected
        assert "api_key" in result.pii_types_found

    def test_secret_key_pattern(self, detector):
        text = "SECRET_KEY=abcdefghijklmnopqrstuvwxyz"
        result = detector.detect(text)
        # Check if detected based on threshold
        assert result.pii_detected


class TestRedaction:
    """Test PII redaction functionality"""

    def test_email_redaction(self, detector):
        text = "Email me at john@example.com"
        result = detector.redact(text)
        assert "[EMAIL_1]" in result.redacted_text
        assert "john@example.com" not in result.redacted_text
        assert result.detection_result.pii_detected

    def test_multiple_same_type_redaction(self, detector):
        text = "alice@test.com and bob@test.com"
        result = detector.redact(text)
        assert "[EMAIL_1]" in result.redacted_text
        assert "[EMAIL_2]" in result.redacted_text

    def test_mixed_pii_redaction(self, detector):
        text = "Contact John at john@test.com or (555) 123-4567"
        result = detector.redact(text)
        assert "[EMAIL_1]" in result.redacted_text
        assert "[PHONE_1]" in result.redacted_text
        assert "john@test.com" not in result.redacted_text
        assert "555" not in result.redacted_text

    def test_no_pii_redaction(self, detector):
        text = "This text has no PII"
        result = detector.redact(text)
        assert result.redacted_text == text
        assert not result.detection_result.pii_detected

    def test_redaction_map_no_actual_pii(self, detector):
        """Ensure redaction map never contains actual PII"""
        text = "My SSN is 123-45-6789 and email is secret@test.com"
        result = detector.redact(text)

        # Redaction map should only have masked placeholders
        for placeholder, value in result.redaction_map.items():
            assert value == "***REDACTED***"
            assert "123-45-6789" not in value
            assert "secret@test.com" not in value


class TestOverlappingPatterns:
    """Test handling of overlapping PII patterns"""

    def test_email_in_text(self, detector):
        # Ensure we handle potential overlaps gracefully
        text = "test@example.com"
        result = detector.redact(text)
        # Should detect as email
        assert result.detection_result.pii_detected
        assert "email" in result.detection_result.pii_types_found

    def test_api_key_with_email_like_pattern(self, detector):
        # Some patterns might have email-like strings
        text = "api_key=sk_test_abcdefghijklmnopqrstuvwxyz"
        result = detector.detect(text)
        # Should handle gracefully
        assert result.pii_detected


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_text(self, detector):
        result = detector.detect("")
        assert not result.pii_detected
        assert result.total_count == 0

    def test_whitespace_only(self, detector):
        result = detector.detect("   \n\t  ")
        assert not result.pii_detected

    def test_very_long_text(self, detector):
        # Ensure performance with long text
        text = "Safe text. " * 10000 + "Email: test@example.com"
        result = detector.detect(text)
        assert result.pii_detected

    def test_unicode_characters(self, detector):
        text = "Email: tëst@example.com"
        detector.detect(text)
        # May or may not match depending on regex

    def test_disabled_detector(self):
        disabled_detector = PIIDetector(enabled=False)
        text = "test@example.com and 123-45-6789"
        result = disabled_detector.detect(text)
        assert not result.pii_detected

    def test_multiple_pii_types(self, detector):
        text = "Email test@example.com, phone (555) 123-4567, SSN 123-45-6789"
        result = detector.detect(text)
        assert result.total_count >= 3
        assert len(result.pii_types_found) >= 3


class TestConfidenceThreshold:
    """Test confidence threshold filtering"""

    def test_high_threshold(self):
        # Very high threshold - only high-confidence matches
        strict_detector = PIIDetector(threshold=0.95)
        text = "Email: test@example.com"
        result = strict_detector.detect(text)
        assert result.pii_detected  # Email has 0.95 confidence

    def test_low_threshold(self):
        # Low threshold - more matches allowed
        lenient_detector = PIIDetector(threshold=0.5)
        text = "api_key: secretkey12345678901234567890"
        result = lenient_detector.detect(text)
        # Should detect API key with lower threshold
        assert result.pii_detected


class TestRealWorldScenarios:
    """Test realistic usage scenarios"""

    def test_customer_support_query(self, detector):
        text = """
        I need help with my order. My email is customer@gmail.com
        and phone number is (555) 123-4567.
        My card ending in 4532015112830366 was charged twice.
        """
        result = detector.redact(text)

        assert result.detection_result.pii_detected
        assert "email" in result.detection_result.pii_types_found
        assert "phone" in result.detection_result.pii_types_found
        assert "credit_card" in result.detection_result.pii_types_found

        # Verify all PII is redacted
        assert "customer@gmail.com" not in result.redacted_text
        assert "(555) 123-4567" not in result.redacted_text
        assert "4532015112830366" not in result.redacted_text

    def test_llm_response_with_pii(self, detector):
        # Simulate LLM accidentally including PII in response
        text = """
        Based on your query, I can help you with that.
        For more information, contact support@company.com
        or call 1-800-555-0199.
        """
        result = detector.redact(text)

        assert result.detection_result.pii_detected
        assert "support@company.com" not in result.redacted_text


class TestLoggingSafety:
    """Ensure logging never exposes actual PII"""

    def test_detection_result_no_pii(self, detector):
        text = "My SSN: 123-45-6789, Email: secret@test.com"
        result = detector.detect(text)

        # DetectionResult should not contain actual PII values
        # Only metadata like type, position, confidence
        for match in result.matches:
            # Match objects have positions but not the actual text
            assert hasattr(match, "pii_type")
            assert hasattr(match, "start_pos")
            assert hasattr(match, "confidence")
            # Verify no PII in match attributes
            assert "123-45-6789" not in str(match)
            assert "secret@test.com" not in str(match)

    def test_redaction_result_safe(self, detector):
        text = "Credit card: 4532015112830366"
        result = detector.redact(text)

        # Redaction map should never contain actual PII
        for placeholder, masked_value in result.redaction_map.items():
            assert masked_value == "***REDACTED***"
            assert "4532015112830366" not in masked_value


class TestLuhnValidation:
    """Test Luhn algorithm for credit card validation"""

    def test_valid_visa(self, detector):
        # Valid Visa card number
        text = "4532015112830366"
        result = detector.detect(text)
        assert result.pii_detected
        assert "credit_card" in result.pii_types_found

    def test_invalid_checksum(self, detector):
        # Invalid checksum (last digit wrong)
        text = "4532015112830365"
        result = detector.detect(text)
        # Should NOT detect due to failed Luhn check
        if result.pii_detected:
            assert "credit_card" not in result.pii_types_found

    def test_valid_mastercard(self, detector):
        # Valid Mastercard
        text = "5425233430109903"
        result = detector.detect(text)
        assert result.pii_detected
        assert "credit_card" in result.pii_types_found


# Run tests with: pytest tests/test_pii_detector.py -v
# Coverage: pytest tests/test_pii_detector.py -v --cov=src/security/pii_detector
