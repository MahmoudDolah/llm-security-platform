#!/usr/bin/env python
"""Quick test script to debug Ollama connection"""
import asyncio
import httpx

async def test_ollama():
    client = httpx.AsyncClient(timeout=30)

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama2",
        "prompt": "What is 2+2?",
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 100,
        }
    }

    print(f"Testing URL: {url}")
    print(f"Payload: {payload}\n")

    try:
        response = await client.post(url, json=payload)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        response.raise_for_status()
    except httpx.HTTPError as e:
        print(f"Error: {e}")
        print(f"Response text: {e.response.text if hasattr(e, 'response') else 'N/A'}")
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_ollama())
