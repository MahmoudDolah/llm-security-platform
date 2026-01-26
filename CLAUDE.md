# CLAUDE.md - Project Context for Claude Code

This file provides context and guidelines for AI assistants (like Claude Code) working on the LLM Security Platform project.

## Project Overview

**LLM Security Platform** is a production-ready security gateway that protects Large Language Model (LLM) applications from adversarial attacks, prompt injections, and abuse. It implements security controls based on the OWASP LLM Top 10.

### Key Goals
1. **Security First**: Protect LLM applications from known attack vectors
2. **Local Development**: Focused on local development and testing
3. **Open Source**: Uses only open source tooling and libraries
4. **Extensible**: Easy to add new LLM backends and security features

## Project Structure

```
llm-security-platform/
├── src/                           # Main application code
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Configuration management using Pydantic
│   ├── llm_client.py             # Abstract LLM client with multiple backends
│   └── security/                  # Security modules
│       ├── __init__.py
│       ├── prompt_injection.py   # Prompt injection detection
│       └── rate_limiter.py       # Rate limiting (token bucket)
├── tests/                         # Test suite
│   └── test_prompt_injection.py  # Security tests (pytest)
├── scripts/                       # Utility scripts
│   └── run_security_tests.py     # Adversarial testing script
├── docs/                         # Documentation
│   ├── GETTING_STARTED.md       # Setup and deployment guide
│   └── ARCHITECTURE.md          # Technical architecture
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
└── README.md                     # Project overview
```

## Core Components

### 1. FastAPI Application (src/main.py)

**Purpose**: Main API server with security middleware

**Key Features**:
- Request processing pipeline with 6 security layers
- Prometheus metrics integration
- Structured logging
- Error handling and rate limit headers

**Security Flow**:
```
Request → Authentication → Rate Limiting → Input Validation 
→ Prompt Injection Detection → Content Filtering → LLM → Response
```

**Important Patterns**:
- Middleware for logging and metrics
- Dependency injection for security components
- Async/await for all I/O operations
- Comprehensive error handling

### 2. Prompt Injection Detector (src/security/prompt_injection.py)

**Purpose**: Detect adversarial prompts using pattern matching

**Detection Categories**:
- Ignore previous instructions
- Role manipulation (DAN mode, etc.)
- System prompt extraction
- Jailbreak attempts
- Code injection
- Context manipulation
- Delimiter-based attacks

**Key Algorithms**:
- Pattern matching with compiled regex
- Confidence scoring (0.0 to 1.0)
- Risk level classification (low/medium/high/critical)
- Category-based severity scoring

**Extensibility**: Add new patterns to `INJECTION_PATTERNS` dict

### 3. Rate Limiter (src/security/rate_limiter.py)

**Purpose**: Prevent abuse using token bucket algorithm

**Implementation**:
- Redis-backed for distributed rate limiting
- Falls back to in-memory if Redis unavailable
- Token bucket algorithm with configurable rate and burst
- Graceful degradation

**Key Classes**:
- `RateLimiter`: Redis-backed distributed limiter
- `InMemoryRateLimiter`: Local development fallback

### 4. PII Detector (src/security/pii_detector.py)

**Purpose**: Detect and redact Personally Identifiable Information (PII)

**Detection Categories**:
- Email addresses (RFC 5322 patterns)
- Phone numbers (US/International formats)
- SSN (Social Security Numbers with validation)
- Credit card numbers (Luhn algorithm validation)
- API keys and secrets (common patterns)

**Key Features**:
- Pattern-based detection with compiled regex
- Confidence scoring per PII type (0.75-0.95)
- Redaction with unique placeholders (`[EMAIL_1]`, `[PHONE_2]`, etc.)
- Privacy-safe logging (never logs actual PII values)
- Dual-scan architecture: input prompts AND LLM responses
- Overlap handling (keeps highest confidence match)

**Security Design**:
- Redaction map stores only masked values (`"***REDACTED***"`)
- Detection results contain positions, not actual values
- Luhn algorithm validation for credit cards (reduces false positives)
- SSN pattern excludes invalid prefixes (000, 666, 9xx)

**Result Dataclasses**:
- `PIIMatch`: Single PII match (type, position, placeholder, confidence)
- `PIIDetectionResult`: Detection summary (pii_detected, matches, types_found, count)
- `PIIRedactionResult`: Redaction output (redacted_text, detection_result, redaction_map)

**Extensibility**: Add new patterns to `PII_PATTERNS` dict with confidence scores

### 5. LLM Client (src/llm_client.py)

**Purpose**: Abstract interface for multiple LLM backends

**Supported Backends**:
- **Ollama**: Local LLM deployment
- **OpenAI**: GPT-3.5, GPT-4, etc.
- **Anthropic**: Claude 3 models

**Design Pattern**: Factory pattern with unified `LLMClient` interface

**Adding New Backends**:
1. Create class inheriting from `LLMClient`
2. Implement `generate()` and `health_check()` methods
3. Add to `LLMClientFactory.create_client()`

### 6. Configuration (src/config.py)

**Purpose**: Centralized configuration using Pydantic Settings

**Configuration Hierarchy**:
- `AppConfig`: Top-level application config
- `SecurityConfig`: Security-related settings
- `LLMConfig`: LLM backend configuration
- `MonitoringConfig`: Logging and metrics

**Environment Variables**: Uses nested delimiter `__` (e.g., `SECURITY__RATE_LIMIT_REQUESTS_PER_MINUTE`)

## Coding Guidelines

### Python Style

**Version**: Python 3.11+

**Style Guide**:
- Follow PEP 8
- Use type hints for all function parameters and returns
- Use dataclasses or Pydantic models for structured data
- Prefer async/await for I/O operations
- Keep functions focused and under 50 lines when possible

**Example**:
```python
async def process_request(prompt: str, api_key: str) -> ChatResponse:
    """
    Process an LLM request with security checks.
    
    Args:
        prompt: User prompt to process
        api_key: Authentication key
        
    Returns:
        ChatResponse with LLM output
        
    Raises:
        HTTPException: If request fails security checks
    """
    # Implementation
```

### Code Organization

**Imports Order**:
1. Standard library
2. Third-party packages
3. Local modules

**Example**:
```python
import time
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import config
from security.prompt_injection import PromptInjectionDetector
```

### Error Handling

**Pattern**: Use FastAPI's `HTTPException` for API errors

```python
# Good
if not valid:
    raise HTTPException(
        status_code=400,
        detail="Clear error message",
        headers={"X-Custom-Header": "value"}
    )

# Bad
return {"error": "Something went wrong"}  # Don't do this
```

### Logging

**Use structured logging** with context:

```python
logger.info(
    "Request processed",
    method=request.method,
    path=request.url.path,
    duration=duration
)

logger.warning(
    "Rate limit exceeded",
    user=user_info["name"],
    retry_after=rate_limit_result.retry_after
)
```

### Testing

**Framework**: pytest with pytest-asyncio

**Test Structure**:
```python
class TestFeatureName:
    """Test suite for feature"""
    
    def test_specific_behavior(self, fixture):
        """Test that specific behavior works correctly"""
        # Arrange
        # Act
        # Assert
```

**Running Tests**:
```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=src --cov-report=html

# Specific test
pytest tests/test_prompt_injection.py::TestSafePrompts::test_simple_question
```

## Common Tasks

### Adding a New LLM Backend

1. **Create client class** in `src/llm_client.py`:
```python
class NewBackendClient(LLMClient):
    def __init__(self, api_key: str, model: str, ...):
        self.api_key = api_key
        self.model = model
    
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        # Implementation
        pass
    
    async def health_check(self) -> bool:
        # Implementation
        pass
```

2. **Add to factory** in `LLMClientFactory.create_client()`:
```python
elif backend == "newbackend":
    return NewBackendClient(
        api_key=kwargs["api_key"],
        model=kwargs.get("model", "default-model")
    )
```

3. **Update configuration** in `src/config.py`:
```python
class LLMConfig(BaseSettings):
    newbackend_api_key: Optional[str] = None
```

4. **Add tests** in `tests/test_llm_client.py`

### Adding a New Attack Pattern

1. **Add pattern** to `INJECTION_PATTERNS` in `src/security/prompt_injection.py`:
```python
"new_attack_type": [
    r"pattern1",
    r"pattern2",
]
```

2. **Add severity score** in `_get_category_severity()`:
```python
severity_map = {
    "new_attack_type": 0.85,
    # ...
}
```

3. **Add test cases** in `tests/test_prompt_injection.py`:
```python
class TestNewAttackType:
    def test_pattern1(self, detector):
        result = detector.detect("trigger pattern1")
        assert result.is_injection
        assert "new_attack_type" in result.detected_patterns
```

### Adding a New API Endpoint

1. **Define request/response models**:
```python
class NewRequest(BaseModel):
    field: str = Field(..., description="Field description")

class NewResponse(BaseModel):
    result: str
```

2. **Create endpoint** in `src/main.py`:
```python
@app.post("/v1/new-endpoint", response_model=NewResponse)
async def new_endpoint(
    request: NewRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    # Validate API key
    user_info = validate_api_key(x_api_key)
    
    # Implement logic
    result = process_request(request)
    
    # Return response
    return NewResponse(result=result)
```

3. **Add tests**
4. **Update API documentation** in README

### Adding Configuration Options

1. **Add to config class** in `src/config.py`:
```python
class SecurityConfig(BaseSettings):
    new_setting: bool = True
    new_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
```

2. **Update .env.example**:
```bash
SECURITY__NEW_SETTING=true
SECURITY__NEW_THRESHOLD=0.5
```

3. **Use in code**:
```python
from config import config

if config.security.new_setting:
    # Use the setting
    pass
```

## Testing Guidelines

### Unit Tests

**Location**: `tests/`

**Coverage Goals**: >80% for security modules

**Key Test Categories**:
- Safe prompts (should NOT be blocked)
- Malicious prompts (SHOULD be blocked)
- Edge cases (empty, very long, unicode)
- Error handling

**Example**:
```python
def test_safe_prompt(self, detector):
    """Safe prompts should not be flagged as injections"""
    result = detector.detect("What is the capital of France?")
    assert not result.is_injection
    assert result.risk_level == "low"
```

### Security Tests

**Location**: `scripts/run_security_tests.py`

**Purpose**: Adversarial testing against live API

**Running**:
```bash
# Start the application first
python src/main.py

# In another terminal
python scripts/run_security_tests.py
```

**Adding Test Cases**:
```python
TEST_CASES.append(
    TestCase(
        name="New Attack",
        category=AttackCategory.PROMPT_INJECTION,
        prompt="Your adversarial prompt here",
        should_block=True,
        description="Description of the attack"
    )
)
```

## Deployment

### Local Development

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env

# Run
cd src
python main.py
```


## Monitoring

### Metrics (Prometheus)

**Endpoint**: `http://localhost:9090/metrics`

**Key Metrics**:
- `llm_requests_total{status, backend}`: Total requests
- `llm_requests_blocked{reason}`: Blocked requests by reason
- `llm_request_duration_seconds`: Request latency histogram
- `llm_prompt_injection_detected{risk_level}`: Injections by risk

### Logs

**Format**: Structured JSON logs

**Key Fields**:
- `event`: Event type
- `level`: Log level (INFO, WARNING, ERROR)
- `timestamp`: ISO timestamp
- Context fields (user, duration, etc.)

### Health Check

**Endpoint**: `http://localhost:8000/health`

**Response**:
```json
{
  "status": "healthy",
  "llm_backend": "ollama",
  "llm_healthy": true,
  "version": "1.0.0"
}
```

## Security Considerations

### Authentication

**Current**: Simple API key validation
**Future**: JWT tokens, OAuth2, role-based access

**API Keys**: Defined in `main.py` (VALID_API_KEYS dict)

### Rate Limiting

**Algorithm**: Token bucket
**Storage**: Redis (distributed) or in-memory (fallback)
**Configuration**: Per-user limits with burst capacity

### Input Validation

**Checks**:
- Prompt length limits
- JSON structure validation
- Character encoding validation

### Secrets Management

**Development**: `.env` file (never commit!)
**Production**: Kubernetes Secrets

## Performance Considerations

### Target Latency
- **Total overhead**: <20ms per request
- **Prompt detection**: <5ms
- **Rate limiting**: <5ms

### Optimization Tips
1. **Use async/await** for all I/O operations
2. **Compile regex patterns** once at startup
3. **Cache frequently accessed data** (Redis)
4. **Connection pooling** for LLM backends
5. **Implement circuit breakers** for external services

## Known Limitations

1. **Pattern-based detection**: May have false positives/negatives
2. **English-only**: Current patterns don't handle non-English well
3. **No ML model**: Using heuristics instead of trained models
4. **Simple auth**: API keys instead of OAuth2
5. **No response filtering**: Only input filtering currently

## Future Enhancements

### High Priority
- [ ] ML-based prompt injection detection
- [ ] Response content filtering
- [ ] More LLM backends (Cohere, Google Gemini)
- [ ] Enhanced PII detection

### Medium Priority
- [ ] Multi-tenancy support
- [ ] Usage analytics dashboard
- [ ] SIEM integration
- [ ] Automated threat response

### Low Priority
- [ ] GraphQL API
- [ ] WebSocket support
- [ ] Admin UI
- [ ] A/B testing framework

## Troubleshooting

### Common Issues

**Port already in use**:
```bash
# Find process using port 8000
lsof -i :8000
# Kill it
kill -9 <PID>
```

**Redis connection fails**:
- Check Redis is running: `redis-cli ping`
- Application will fall back to in-memory rate limiter

**Ollama not found**:
- Install: `brew install ollama` or download from ollama.ai
- Start: `ollama serve`
- Pull model: `ollama pull llama2`

**Import errors**:
- Check you're in virtual environment: `which python`
- Reinstall dependencies: `pip install -r requirements.txt`

### Debug Mode

Enable debug logging:
```bash
MONITORING__LOG_LEVEL=DEBUG python src/main.py
```

## Questions to Ask

When working on this project, consider:

1. **Security**: Does this change introduce new attack vectors?
2. **Performance**: Will this add significant latency?
3. **Testing**: What test cases are needed?
4. **Documentation**: Should docs be updated?
5. **Breaking Changes**: Is this backward compatible?

## Resources

### Documentation
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Kubernetes Docs](https://kubernetes.io/docs/)
- [Prometheus Metrics](https://prometheus.io/docs/)

### Internal Docs
- `docs/GETTING_STARTED.md`: Setup and deployment
- `docs/ARCHITECTURE.md`: System architecture
- `README.md`: Project overview

## Contact

- **Author**: Mahmoud Dolah
- **Email**: mahmoudamindolah@gmail.com
- **GitHub**: github.com/mahmouddolah
- **Blog**: www.dolah.dev

---

## Quick Command Reference

```bash
# Development
python src/main.py                    # Run application
pytest tests/ -v                      # Run tests
python scripts/run_security_tests.py  # Security tests

# Testing
curl http://localhost:8000/health
curl -X POST http://localhost:8000/v1/chat \
  -H "X-API-Key: test-key-1" \
  -d '{"prompt": "Hello!"}'
```

---

**Remember**: This is a security-focused project. Always think about potential attack vectors and edge cases when making changes!