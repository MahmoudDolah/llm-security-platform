"""
Main FastAPI Application

LLM Security Platform - Production-ready security gateway for LLM applications.
"""
import time
import structlog
from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from config import config
from security.prompt_injection import PromptInjectionDetector
from security.rate_limiter import RateLimiter, InMemoryRateLimiter
from llm_client import LLMClientFactory

# Initialize logging
logger = structlog.get_logger()

# Initialize metrics (with guards to prevent duplicate registration)
try:
    REQUEST_COUNT = Counter(
        'llm_requests_total',
        'Total number of LLM requests',
        ['status', 'backend']
    )
    REQUEST_BLOCKED = Counter(
        'llm_requests_blocked',
        'Number of blocked requests',
        ['reason']
    )
    REQUEST_DURATION = Histogram(
        'llm_request_duration_seconds',
        'Request duration in seconds'
    )
    PROMPT_INJECTION_DETECTED = Counter(
        'llm_prompt_injection_detected',
        'Number of prompt injections detected',
        ['risk_level']
    )
except ValueError:
    # Metrics already registered (happens with hot reload)
    from prometheus_client import REGISTRY
    REQUEST_COUNT = REGISTRY._names_to_collectors.get('llm_requests_total')
    REQUEST_BLOCKED = REGISTRY._names_to_collectors.get('llm_requests_blocked')
    REQUEST_DURATION = REGISTRY._names_to_collectors.get('llm_request_duration_seconds')
    PROMPT_INJECTION_DETECTED = REGISTRY._names_to_collectors.get('llm_prompt_injection_detected')

# Initialize FastAPI app
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="Production-ready security gateway for LLM applications"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize security components
try:
    rate_limiter = RateLimiter(
        redis_url=config.redis_url,
        requests_per_minute=config.security.rate_limit_requests_per_minute,
        burst_size=config.security.rate_limit_burst_size
    )
    logger.info("Rate limiter initialized with Redis")
except Exception as e:
    logger.warning(f"Failed to connect to Redis, using in-memory rate limiter: {e}")
    rate_limiter = InMemoryRateLimiter(
        requests_per_minute=config.security.rate_limit_requests_per_minute,
        burst_size=config.security.rate_limit_burst_size
    )

prompt_detector = PromptInjectionDetector(
    threshold=config.security.prompt_injection_threshold
)

# Initialize LLM client
llm_client = LLMClientFactory.create_client(
    backend=config.llm.backend,
    ollama_base_url=config.llm.ollama_base_url,
    model=config.llm.model,
    timeout=config.llm.timeout,
    max_tokens=config.llm.max_tokens,
    temperature=config.llm.temperature,
    api_key=config.llm.openai_api_key or config.llm.anthropic_api_key
)

logger.info(
    "LLM Security Platform initialized",
    backend=config.llm.backend,
    model=config.llm.model
)


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request model"""
    prompt: str = Field(..., min_length=1, max_length=10000)
    max_tokens: Optional[int] = Field(None, ge=1, le=4000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    model: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    model: str
    tokens_used: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None
    code: str


# Simple API key validation (in production, use proper auth)
VALID_API_KEYS = {
    "test-key-1": {"name": "Test User 1", "tier": "free"},
    "test-key-2": {"name": "Test User 2", "tier": "premium"},
}


def validate_api_key(api_key: Optional[str]) -> Dict[str, Any]:
    """Validate API key and return user info"""
    if not config.security.require_authentication:
        return {"name": "Anonymous", "tier": "free"}
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-Key header."
        )
    
    user_info = VALID_API_KEYS.get(api_key)
    if not user_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return user_info


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests"""
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    logger.info(
        "Request processed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration=duration
    )
    
    REQUEST_DURATION.observe(duration)
    
    return response


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Send a prompt to the LLM with security controls.
    
    Security layers:
    1. Authentication
    2. Rate limiting
    3. Input validation
    4. Prompt injection detection
    5. Content filtering
    """
    
    # 1. Authentication
    user_info = validate_api_key(x_api_key)
    user_id = x_api_key or "anonymous"
    
    # 2. Rate Limiting
    rate_limit_result = rate_limiter.check_rate_limit(user_id)
    if not rate_limit_result.allowed:
        REQUEST_BLOCKED.labels(reason="rate_limit").inc()
        logger.warning(
            "Rate limit exceeded",
            user=user_info["name"],
            retry_after=rate_limit_result.retry_after
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {rate_limit_result.retry_after} seconds.",
            headers={
                "X-RateLimit-Remaining": str(rate_limit_result.remaining),
                "X-RateLimit-Reset": str(rate_limit_result.reset_time),
                "Retry-After": str(rate_limit_result.retry_after)
            }
        )
    
    # 3. Input Validation
    if len(request.prompt) > config.security.max_prompt_length:
        REQUEST_BLOCKED.labels(reason="prompt_too_long").inc()
        raise HTTPException(
            status_code=400,
            detail=f"Prompt exceeds maximum length of {config.security.max_prompt_length} characters"
        )
    
    # 4. Prompt Injection Detection
    if config.security.prompt_injection_enabled:
        detection_result = prompt_detector.detect(request.prompt)
        
        if detection_result.is_injection:
            REQUEST_BLOCKED.labels(reason="prompt_injection").inc()
            PROMPT_INJECTION_DETECTED.labels(
                risk_level=detection_result.risk_level
            ).inc()
            
            logger.warning(
                "Prompt injection detected",
                user=user_info["name"],
                confidence=detection_result.confidence,
                risk_level=detection_result.risk_level,
                patterns=detection_result.detected_patterns
            )
            
            raise HTTPException(
                status_code=400,
                detail=prompt_detector.get_safe_response(detection_result),
                headers={"X-Security-Risk": detection_result.risk_level}
            )
    
    # 5. Forward to LLM
    try:
        # Build kwargs for LLM client, only including non-None values
        llm_kwargs = {"prompt": request.prompt}
        if request.max_tokens is not None:
            llm_kwargs["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            llm_kwargs["temperature"] = request.temperature
        if request.model is not None:
            llm_kwargs["model"] = request.model

        llm_response = await llm_client.generate(**llm_kwargs)
        
        REQUEST_COUNT.labels(
            status="success",
            backend=config.llm.backend
        ).inc()
        
        logger.info(
            "LLM request successful",
            user=user_info["name"],
            tokens=llm_response.tokens_used,
            model=llm_response.model
        )
        
        return ChatResponse(
            response=llm_response.content,
            model=llm_response.model,
            tokens_used=llm_response.tokens_used,
            metadata={
                "remaining_requests": rate_limit_result.remaining,
                "user_tier": user_info["tier"]
            }
        )
    
    except Exception as e:
        REQUEST_COUNT.labels(
            status="error",
            backend=config.llm.backend
        ).inc()
        
        logger.error(
            "LLM request failed",
            user=user_info["name"],
            error=str(e)
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"LLM request failed: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    llm_healthy = await llm_client.health_check()
    
    return {
        "status": "healthy" if llm_healthy else "degraded",
        "llm_backend": config.llm.backend,
        "llm_healthy": llm_healthy,
        "version": config.app_version
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": config.app_name,
        "version": config.app_version,
        "description": "Production-ready security gateway for LLM applications",
        "endpoints": {
            "chat": "/v1/chat",
            "health": "/health",
            "metrics": "/metrics"
        },
        "security_features": [
            "Authentication (API Key)",
            "Rate Limiting (Token Bucket)",
            "Prompt Injection Detection",
            "Input Validation",
            "Comprehensive Logging",
            "Metrics & Monitoring"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        workers=config.workers,
        log_level=config.monitoring.log_level.lower()
    )
