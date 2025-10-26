# LLM Security Platform - Architecture Overview

## System Architecture

The LLM Security Platform is a production-ready security gateway designed to protect Large Language Model (LLM) applications from adversarial attacks and abuse.

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Applications                      │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/HTTPS + API Key
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Load Balancer / Ingress                       │
│                    (Nginx Ingress Controller)                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                              ▼
┌──────────────────────┐      ┌──────────────────────┐
│  Security Gateway    │      │  Security Gateway    │
│    (Pod 1)           │ ...  │    (Pod N)           │
│                      │      │                      │
│  ┌────────────────┐  │      │  ┌────────────────┐  │
│  │ 1. Auth        │  │      │  │ 1. Auth        │  │
│  │ 2. Rate Limit  │  │      │  │ 2. Rate Limit  │  │
│  │ 3. Detection   │  │      │  │ 3. Detection   │  │
│  │ 4. Validation  │  │      │  │ 4. Validation  │  │
│  │ 5. Filtering   │  │      │  │ 5. Filtering   │  │
│  │ 6. Logging     │  │      │  │ 6. Logging     │  │
│  └────────────────┘  │      │  └────────────────┘  │
└──────────┬───────────┘      └──────────┬───────────┘
           │                              │
           │     ┌────────────────────┐   │
           └────▶│      Redis         │◀──┘
                 │  (Rate Limiting)   │
                 └────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LLM Backend                                │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │  Ollama    │  │  OpenAI    │  │ Anthropic  │                │
│  │  (Local)   │  │   API      │  │   Claude   │                │
│  └────────────┘  └────────────┘  └────────────┘                │
└─────────────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Observability & Monitoring                          │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │ Prometheus │  │  DataDog   │  │ Structured │                │
│  │  Metrics   │  │    APM     │  │   Logs     │                │
│  └────────────┘  └────────────┘  └────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Security Gateway (FastAPI Application)

The heart of the platform, implementing multiple security layers:

#### Request Processing Flow
```
Incoming Request
    │
    ▼
[1] Authentication
    │ ✓ Valid API Key?
    ▼
[2] Rate Limiting
    │ ✓ Within rate limits?
    ▼
[3] Input Validation
    │ ✓ Valid format & length?
    ▼
[4] Prompt Injection Detection
    │ ✓ No adversarial patterns?
    ▼
[5] Content Filtering
    │ ✓ No PII/malicious content?
    ▼
[6] Forward to LLM
    │
    ▼
[7] Response Processing
    │
    ▼
[8] Logging & Metrics
    │
    ▼
Return to Client
```

### 2. Security Modules

#### Prompt Injection Detector
- **Technology**: Pattern matching + heuristics
- **Coverage**: OWASP LLM01 attack vectors
- **Performance**: <5ms per detection
- **Patterns Detected**:
  - Ignore previous instructions
  - Role manipulation (DAN mode, etc.)
  - System prompt extraction
  - Jailbreak attempts
  - Code injection
  - Context manipulation

#### Rate Limiter
- **Algorithm**: Token bucket
- **Storage**: Redis (distributed) or in-memory
- **Granularity**: Per API key / user
- **Configuration**: 
  - Requests per minute
  - Burst size
  - Different tiers (free, premium)

### 3. LLM Client Abstraction

Unified interface for multiple LLM backends:

```python
# Supports multiple backends with same interface
client = LLMClientFactory.create_client(
    backend="ollama",  # or "openai", "anthropic"
    model="llama2",
    # ... config
)

response = await client.generate(prompt="Hello")
```

**Supported Backends:**
- Ollama (local deployment)
- OpenAI (GPT-3.5, GPT-4)
- Anthropic (Claude 3)

### 4. Monitoring & Observability

#### Metrics (Prometheus)
```python
# Key metrics exposed
llm_requests_total{status, backend}
llm_requests_blocked{reason}
llm_request_duration_seconds
llm_prompt_injection_detected{risk_level}
```

#### Structured Logging
- All requests logged with context
- Security events highlighted
- Searchable and analyzable

## Deployment Architecture

### Kubernetes Deployment

```
┌─────────────────────────────────────────────────────┐
│                 Kubernetes Cluster                  │
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │           llm-security Namespace             │  │
│  │                                              │  │
│  │  ┌────────────────────────────────────────┐ │  │
│  │  │      Security Gateway Deployment       │ │  │
│  │  │                                        │ │  │
│  │  │  ┌──────┐  ┌──────┐  ┌──────┐        │ │  │
│  │  │  │ Pod1 │  │ Pod2 │  │ Pod3 │  ...   │ │  │
│  │  │  └──────┘  └──────┘  └──────┘        │ │  │
│  │  │                                        │ │  │
│  │  │  HPA: 3-10 pods (CPU/Memory based)    │ │  │
│  │  └────────────────────────────────────────┘ │  │
│  │                                              │  │
│  │  ┌────────────────────────────────────────┐ │  │
│  │  │          Redis Deployment              │ │  │
│  │  │  (Rate limiting & caching)             │ │  │
│  │  └────────────────────────────────────────┘ │  │
│  │                                              │  │
│  │  ┌────────────────────────────────────────┐ │  │
│  │  │      Services & Ingress               │ │  │
│  │  │  - ClusterIP service (internal)        │ │  │
│  │  │  - Ingress (external HTTPS)            │ │  │
│  │  └────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

#### Deployment Features
- **High Availability**: 3+ replicas with PodDisruptionBudget
- **Auto-scaling**: HPA based on CPU/memory (3-10 pods)
- **Rolling Updates**: Zero-downtime deployments
- **Health Checks**: Liveness and readiness probes
- **Resource Limits**: CPU and memory constraints
- **Security**: Non-root user, security contexts

### CI/CD Pipeline (GitHub Actions)

```
Code Push
    │
    ▼
┌─────────────────┐
│   Run Tests     │  Unit tests, coverage
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Security Scan   │  Trivy, code analysis
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Lint Code     │  Black, Flake8, MyPy
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Build Image    │  Docker build & push
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Deploy to K8s  │  kubectl apply or ArgoCD
└─────────────────┘
```

## Security Architecture

### Defense in Depth

Multiple layers of security controls:

1. **Network Layer**
   - TLS/HTTPS encryption
   - Rate limiting at ingress
   - DDoS protection

2. **Authentication Layer**
   - API key validation
   - Role-based access (free/premium tiers)
   - Key rotation support

3. **Application Layer**
   - Prompt injection detection
   - Input validation
   - Content filtering
   - Output sanitization

4. **Infrastructure Layer**
   - Kubernetes security contexts
   - Non-root containers
   - Network policies
   - Secret management

### Security Controls Mapping

| OWASP LLM Top 10 | Control | Implementation |
|------------------|---------|----------------|
| LLM01: Prompt Injection | Detection | Pattern matching + ML |
| LLM02: Insecure Output | Filtering | Response validation |
| LLM03: Training Data Poisoning | N/A | Backend responsibility |
| LLM04: Model DoS | Rate Limiting | Token bucket algorithm |
| LLM05: Supply Chain | Scanning | Trivy, dependency checks |
| LLM06: Sensitive Info | PII Detection | Presidio integration |
| LLM07: Insecure Plugins | N/A | No plugin support |
| LLM08: Excessive Agency | Validation | Request validation |
| LLM09: Overreliance | Logging | Audit trails |
| LLM10: Model Theft | Auth | API key required |

## Data Flow

### Request Processing

```
1. Client sends request with API key
   POST /v1/chat
   Headers: X-API-Key: xxx
   Body: { "prompt": "..." }

2. Gateway validates API key
   → Check against valid keys store
   → Extract user tier and limits

3. Rate limiter checks limits
   → Query Redis for token bucket state
   → Update bucket (consume token or deny)

4. Prompt injection detector analyzes input
   → Pattern matching against attack signatures
   → Calculate confidence score
   → Block if above threshold

5. Input validation
   → Check prompt length
   → Validate JSON structure
   → Sanitize special characters

6. Forward to LLM backend
   → Route based on configuration
   → Add timeout handling
   → Circuit breaker pattern

7. Process LLM response
   → Extract content
   → Optional response filtering
   → Add metadata

8. Log and emit metrics
   → Structured logging
   → Prometheus metrics
   → Optional DataDog APM

9. Return to client
   → Format response
   → Add rate limit headers
   → Return 200 or error code
```

## Scalability

### Horizontal Scaling

- **Stateless Design**: Each pod is identical and stateless
- **Shared State**: Redis for distributed rate limiting
- **Load Balancing**: Kubernetes Service distributes traffic
- **Auto-scaling**: HPA adds/removes pods based on metrics

### Performance Characteristics

| Component | Latency | Throughput |
|-----------|---------|------------|
| Authentication | <1ms | 10,000+ req/s |
| Rate Limiting | <5ms | 5,000+ req/s |
| Prompt Detection | <5ms | 5,000+ req/s |
| Total Overhead | <20ms | 1,000+ req/s per pod |

### Capacity Planning

**Per Pod:**
- CPU: 250m request, 500m limit
- Memory: 256Mi request, 512Mi limit
- Concurrent requests: ~50-100

**Cluster (3-10 pods):**
- Minimum throughput: 3,000 req/s
- Maximum throughput: 10,000 req/s
- Supports 50,000+ users with rate limiting

## Technology Stack

### Core Technologies
- **FastAPI**: Modern, high-performance web framework
- **Python 3.11**: Latest stable Python
- **Redis**: Distributed caching and rate limiting
- **Kubernetes**: Container orchestration
- **ArgoCD**: GitOps deployment

### Security Libraries
- **Presidio**: PII detection
- **LangKit**: LLM observability
- **Custom detectors**: Prompt injection patterns

### Monitoring
- **Prometheus**: Metrics collection
- **Grafana**: Metrics visualization
- **DataDog**: Optional APM
- **Structlog**: Structured logging

### CI/CD
- **GitHub Actions**: Automated pipelines
- **Trivy**: Security scanning
- **Docker**: Containerization
- **Helm**: Package management (future)

## Future Enhancements

### Planned Features
1. **Advanced ML Detection**
   - Train custom models for prompt injection
   - Use transformers for semantic analysis

2. **Response Filtering**
   - PII redaction in responses
   - Content moderation
   - Toxicity detection

3. **Multi-tenancy**
   - Tenant isolation
   - Per-tenant configuration
   - Usage tracking and billing

4. **Integration Ecosystem**
   - SIEM integration (Splunk, ELK)
   - API gateway plugins (Kong, Envoy)
   - Cloud provider integrations

5. **Advanced Analytics**
   - Attack pattern analysis
   - User behavior analytics
   - Automated threat response

## References

- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [Prometheus Monitoring](https://prometheus.io/docs/introduction/overview/)
