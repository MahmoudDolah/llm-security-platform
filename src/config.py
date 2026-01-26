"""
Configuration management for LLM Security Platform
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class SecurityConfig(BaseSettings):
    """Security configuration settings"""

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(default=60, ge=1)
    rate_limit_burst_size: int = Field(default=10, ge=1)

    # Prompt Injection Detection
    prompt_injection_enabled: bool = True
    prompt_injection_threshold: float = Field(default=0.8, ge=0.0, le=1.0)

    # PII Detection & Redaction
    pii_detection_enabled: bool = True
    pii_detection_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    pii_redact_requests: bool = True  # Redact PII in incoming prompts
    pii_redact_responses: bool = True  # Redact PII in LLM responses
    pii_log_detections: bool = True  # Log PII detection events (without actual values)

    # Specific PII types to detect (allow disabling specific types)
    pii_detect_email: bool = True
    pii_detect_phone: bool = True
    pii_detect_ssn: bool = True
    pii_detect_credit_card: bool = True
    pii_detect_api_key: bool = True

    # Content Filtering
    block_pii: bool = True
    block_profanity: bool = True
    max_prompt_length: int = Field(default=4000, ge=100)

    # Authentication
    api_key_header: str = "X-API-Key"
    require_authentication: bool = True


class LLMConfig(BaseSettings):
    """LLM backend configuration"""

    backend: str = Field(default="ollama")  # ollama, openai, anthropic
    model: str = Field(default="llama2")
    timeout: int = Field(default=30, ge=5)
    max_tokens: int = Field(default=1000, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # API Keys (from environment)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"


class MonitoringConfig(BaseSettings):
    """Monitoring and logging configuration"""

    log_level: str = "INFO"
    log_format: str = "json"

    # Metrics
    enable_prometheus: bool = True
    metrics_port: int = 9090


class AppConfig(BaseSettings):
    """Main application configuration"""

    app_name: str = "LLM Security Platform"
    app_version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # Redis for rate limiting and caching
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl: int = Field(default=3600, ge=0)

    # Sub-configurations
    security: SecurityConfig = SecurityConfig()
    llm: LLMConfig = LLMConfig()
    monitoring: MonitoringConfig = MonitoringConfig()

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"
        case_sensitive = False


# Global config instance
config = AppConfig()
