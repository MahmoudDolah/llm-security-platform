"""
PII Detection and Redaction Module

Detects and redacts Personally Identifiable Information (PII) in text.
Based on OWASP LLM Top 10 - LLM06: Sensitive Information Disclosure.
"""

import re
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class PIIMatch:
    """Represents a single PII match in text"""

    pii_type: str  # email, phone, ssn, credit_card, api_key
    start_pos: int
    end_pos: int
    placeholder: str  # e.g., "[EMAIL_1]", "[PHONE_2]"
    confidence: float  # 0.0 to 1.0


@dataclass
class PIIDetectionResult:
    """Result of PII detection scan"""

    pii_detected: bool
    matches: List[PIIMatch]
    pii_types_found: List[str]  # Unique PII types detected
    total_count: int  # Total number of PII instances


@dataclass
class PIIRedactionResult:
    """Result of PII redaction operation"""

    original_length: int
    redacted_text: str
    detection_result: PIIDetectionResult
    redaction_map: Dict[str, str]  # placeholder -> "***REDACTED***" (for logging)


class PIIDetector:
    """
    Detects and redacts PII using pattern matching.

    Detection Categories:
    - Email addresses (RFC 5322 simplified)
    - Phone numbers (US/International formats)
    - SSN (Social Security Numbers)
    - Credit card numbers (Luhn algorithm validation)
    - API keys/secrets (common patterns)

    Privacy Design:
    - Never logs actual PII values
    - Redaction map stores only masked placeholders
    - Detection results contain positions, not actual values
    """

    # Pattern definitions with confidence scores
    PII_PATTERNS = {
        "email": {
            "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "confidence": 0.95,
            "flags": 0,
        },
        "phone": {
            # Matches: (555) 123-4567, 555-123-4567, +1-555-123-4567
            "pattern": (
                r"(?:\+?1[-.\s]?)?(?:\([0-9]{3}\)|[0-9]{3})[-.\s]?"
                r"[0-9]{3}[-.\s]?[0-9]{4}\b"
            ),
            "confidence": 0.90,
            "flags": 0,
        },
        "ssn": {
            # Matches: 123-45-6789, 123 45 6789
            # Excludes invalid SSN patterns (000, 666, 9xx prefixes)
            "pattern": (
                r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?" r"(?!0000)\d{4}\b"
            ),
            "confidence": 0.85,
            "flags": 0,
        },
        "credit_card": {
            # Matches major card formats (Visa, MC, Amex, Discover)
            # Will be validated with Luhn algorithm
            "pattern": (
                r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|"
                r"3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b"
            ),
            "confidence": 0.95,  # High confidence due to Luhn validation
            "flags": 0,
        },
        "api_key": {
            # Matches common API key patterns (AWS, GitHub, OpenAI, etc.)
            "pattern": (
                r"(?i)(?:api[_-]?key|apikey|access[_-]?token|"
                r"secret[_-]?key|private[_-]?key)[\s:=]+['\"]?"
                r"([A-Za-z0-9_\-]{20,})['\"]?"
            ),
            "confidence": 0.75,
            "flags": re.IGNORECASE,
        },
    }

    def __init__(self, enabled: bool = True, threshold: float = 0.75):
        """
        Initialize PII detector.

        Args:
            enabled: Whether PII detection is active
            threshold: Minimum confidence to consider a match (0.0 to 1.0)
        """
        self.enabled = enabled
        self.threshold = threshold
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for performance"""
        self.compiled_patterns = {}
        for pii_type, config in self.PII_PATTERNS.items():
            self.compiled_patterns[pii_type] = {
                "regex": re.compile(config["pattern"], config["flags"]),
                "confidence": config["confidence"],
            }

    def _luhn_check(self, card_number: str) -> bool:
        """
        Validate credit card number using Luhn algorithm.
        Reduces false positives for credit card detection.

        Args:
            card_number: Credit card number string

        Returns:
            True if valid per Luhn algorithm, False otherwise
        """
        # Remove spaces and dashes
        card_number = card_number.replace(" ", "").replace("-", "")

        def digits_of(n):
            return [int(d) for d in str(n)]

        digits = digits_of(card_number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        return checksum % 10 == 0

    def detect(self, text: str) -> PIIDetectionResult:
        """
        Detect PII in text without modifying it.

        Args:
            text: Text to scan for PII

        Returns:
            PIIDetectionResult with detected PII information
        """
        if not self.enabled or not text:
            return PIIDetectionResult(
                pii_detected=False, matches=[], pii_types_found=[], total_count=0
            )

        matches = []

        # Process patterns in order of specificity
        # More specific patterns (credit_card, ssn) before general ones (phone)
        pattern_order = ["email", "ssn", "credit_card", "api_key", "phone"]

        for pii_type in pattern_order:
            if pii_type not in self.compiled_patterns:
                continue

            compiled = self.compiled_patterns[pii_type]
            regex = compiled["regex"]
            confidence = compiled["confidence"]

            # Skip if below threshold
            if confidence < self.threshold:
                continue

            for match in regex.finditer(text):
                # Special handling for credit cards (validate with Luhn)
                if pii_type == "credit_card":
                    if not self._luhn_check(match.group(0)):
                        continue  # Skip false positive

                matches.append(
                    PIIMatch(
                        pii_type=pii_type,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        placeholder="",  # Will be set during redaction
                        confidence=confidence,
                    )
                )

        # Sort matches by position to handle overlaps
        matches.sort(key=lambda m: m.start_pos)

        # Remove overlapping matches (keep higher confidence)
        matches = self._remove_overlaps(matches)

        pii_types = list(set(m.pii_type for m in matches))

        return PIIDetectionResult(
            pii_detected=len(matches) > 0,
            matches=matches,
            pii_types_found=pii_types,
            total_count=len(matches),
        )

    def _remove_overlaps(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """
        Remove overlapping matches, keeping higher confidence ones.

        Important for cases like:
        - "api_key=user@example.com" (could match both api_key and email)

        Args:
            matches: List of PIIMatch objects sorted by start_pos

        Returns:
            List of non-overlapping PIIMatch objects
        """
        if not matches:
            return matches

        non_overlapping: List[PIIMatch] = []
        for match in matches:
            # Check if this match overlaps with any accepted match
            overlaps = False
            for accepted in non_overlapping:
                if (
                    match.start_pos < accepted.end_pos
                    and match.end_pos > accepted.start_pos
                ):
                    # Overlaps - keep the one with higher confidence
                    if match.confidence > accepted.confidence:
                        non_overlapping.remove(accepted)
                        break
                    else:
                        overlaps = True
                        break

            if not overlaps:
                non_overlapping.append(match)

        return non_overlapping

    def redact(self, text: str) -> PIIRedactionResult:
        """
        Detect and redact PII in text.

        Args:
            text: Text to redact

        Returns:
            PIIRedactionResult with redacted text and metadata
        """
        detection_result = self.detect(text)

        if not detection_result.pii_detected:
            return PIIRedactionResult(
                original_length=len(text),
                redacted_text=text,
                detection_result=detection_result,
                redaction_map={},
            )

        # Build redacted text by replacing PII with placeholders
        redacted_text = text
        redaction_map = {}
        offset = 0  # Track position changes from replacements

        # Count occurrences of each PII type for unique placeholders
        pii_counters: Dict[str, int] = {}

        for match in detection_result.matches:
            # Generate unique placeholder
            pii_counters[match.pii_type] = pii_counters.get(match.pii_type, 0) + 1
            placeholder = f"[{match.pii_type.upper()}_{pii_counters[match.pii_type]}]"

            # Update match with placeholder
            match.placeholder = placeholder

            # Calculate actual positions with offset
            actual_start = match.start_pos + offset
            actual_end = match.end_pos + offset

            # Store masked version for logging (never store actual PII)
            redaction_map[placeholder] = "***REDACTED***"

            # Perform replacement
            redacted_text = (
                redacted_text[:actual_start] + placeholder + redacted_text[actual_end:]
            )

            # Update offset for next replacement
            offset += len(placeholder) - (match.end_pos - match.start_pos)

        return PIIRedactionResult(
            original_length=len(text),
            redacted_text=redacted_text,
            detection_result=detection_result,
            redaction_map=redaction_map,
        )


# Example usage and testing
if __name__ == "__main__":
    detector = PIIDetector(enabled=True, threshold=0.75)

    # Test cases
    test_prompts = [
        "Email me at john.doe@example.com",
        "Call me at (555) 123-4567",
        "My SSN is 123-45-6789",
        "Card number: 4532015112830366",
        "No PII in this text",
    ]

    print("PII Detection and Redaction Tests\n" + "=" * 50)
    for prompt in test_prompts:
        result = detector.redact(prompt)
        print(f"\nOriginal: {prompt}")
        print(f"Redacted: {result.redacted_text}")
        print(f"PII Found: {result.detection_result.pii_types_found}")
        print(f"Count: {result.detection_result.total_count}")
