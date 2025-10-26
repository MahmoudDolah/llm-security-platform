# LLM Security Platform

A production-ready security gateway for Large Language Model (LLM) applications that protects against adversarial attacks, prompt injections, and other security threats.

## Overview

This platform provides a secure API gateway that sits between client applications and LLM backends, implementing multiple layers of security controls based on the OWASP Top 10 for LLM Applications.

## Features

### Core Security Controls
- **Prompt Injection Detection**: Identifies and blocks common prompt injection patterns
- **Input Validation**: Validates and sanitizes user inputs before reaching the LLM
- **Rate Limiting**: Prevents abuse through configurable rate limits per user/API key
- **Authentication & Authorization**: API key-based authentication with role-based access
- **Content Filtering**: Detects and blocks malicious content, PII, and sensitive data
- **Adversarial Attack Detection**: Identifies jailbreak attempts and adversarial prompts

### Operational Features
- **Comprehensive Logging**: Detailed request/response logging for security auditing
- **Metrics & Monitoring**: Prometheus-compatible metrics for observability
- **Circuit Breaking**: Protects backend LLM services from overload
- **Request/Response Caching**: Improves performance and reduces costs
- **Kubernetes-Native**: Designed for cloud-native deployments

## Architecture

```
Client → Security Gateway (FastAPI) → LLM Backend (Ollama/OpenAI/Claude)
              ↓
         Logging & Monitoring (Prometheus/DataDog)
```

## Quick Start

### Prerequisites
- Python 3.9+
- Docker & Kubernetes (for deployment)
- Ollama (for local LLM) or API keys for OpenAI/Anthropic

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run the security gateway
python src/main.py

# Run tests
pytest tests/
```

### Kubernetes Deployment

```bash
# Build and push Docker image
docker build -t llm-security-gateway:latest .
docker push your-registry/llm-security-gateway:latest

# Deploy to Kubernetes
kubectl apply -f k8s/

# Or use ArgoCD for GitOps
argocd app create llm-security-platform \
  --repo https://github.com/yourusername/llm-security-platform \
  --path k8s \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace llm-security
```

## Configuration

Configuration is managed through environment variables and `config.yaml`:

```yaml
security:
  rate_limit:
    requests_per_minute: 60
    burst_size: 10
  
  prompt_injection:
    enabled: true
    confidence_threshold: 0.8
  
  content_filtering:
    block_pii: true
    block_profanity: true

llm:
  backend: ollama  # or openai, anthropic
  model: llama2
  timeout: 30
```

## Security Testing

The platform includes an automated security testing framework:

```bash
# Run adversarial tests
python scripts/run_security_tests.py

# Test specific attack vectors
python scripts/test_prompt_injection.py
```

## API Documentation

### Authentication
All requests require an API key in the header:
```bash
curl -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "What is the capital of France?"}' \
     http://localhost:8000/v1/chat
```

### Endpoints

- `POST /v1/chat` - Send a prompt to the LLM
- `GET /health` - Health check endpoint
- `GET /metrics` - Prometheus metrics

## Monitoring

The platform exposes Prometheus metrics:
- `llm_requests_total` - Total number of requests
- `llm_requests_blocked` - Number of blocked requests
- `llm_request_duration_seconds` - Request latency
- `llm_prompt_injection_detected` - Prompt injection detections

## Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.

## License

MIT License - See LICENSE file for details

## Security

For security issues, please email mahmoudamindolah@gmail.com instead of using the issue tracker.

## Roadmap

- [ ] Additional LLM backend support (Google Gemini, Cohere)
- [ ] Advanced adversarial detection using ML models
- [ ] Integration with SIEM systems
- [ ] Automated security reporting
- [ ] Multi-tenant support with tenant isolation
- [ ] Response filtering and sanitization
- [ ] Token usage tracking and billing
