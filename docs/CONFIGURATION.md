# Configuration Guide

The Code Assistant is highly configurable via environment variables and project files. This document details the settings required to connect to LLM providers, define fallback models, and adjust rate limit and logging behaviors.

---

## 1. Environment Variables Setup

Create a `.env` file in the project root directory. You can use the following variables:

```ini
# LLM Provider Selection & Credentials
OPENROUTER_API_KEY=your-openrouter-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
OPENAI_API_KEY=your-openai-key-here

# Target Model Specification (Defaults below if not specified)
# Venice/OpenRouter Llama-3.3-70b-instruct is highly recommended for free tier usage
LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Logging and Debugging Configuration
LOG_LEVEL=INFO
```

---

## 2. LLM Provider Routing

The agents route their API calls dynamically based on which credentials and client interfaces are available:

### Provider Precedence

1. **Anthropic (`AsyncAnthropic`)**:
   - Activated if `ANTHROPIC_API_KEY` is present.
   - Default Model: `claude-sonnet-4-20250514` (Claude 3.5 Sonnet).
2. **OpenAI / OpenRouter (`AsyncOpenAI`)**:
   - Activated if `OPENAI_API_KEY` or `OPENROUTER_API_KEY` is present.
   - If using OpenRouter, the client base URL points to `https://openrouter.ai/api/v1`.
   - Default Model: `meta-llama/llama-3.3-70b-instruct:free` (if `LLM_MODEL` is set in `.env`) or `gpt-4o`.

### Dry-Run & Test Fallback

If no valid API keys are present (or if the key is set to a placeholder like `test-key`), the agents automatically fall back to the **Mock LLM Response Generator**. This is ideal for:
- Executing dry runs of the agent state machine.
- Running unit tests without invoking paid API endpoints.
- Verifying the LangGraph pipeline topology.

---

## 3. Rate Limit Handling & Backoff

To prevent failures due to OpenAI/OpenRouter rate-limits (standard `HTTP 429` errors), the base agent implements a robust retry mechanism:

- **Max Retries**: 5 attempts.
- **Base Exponential Delay**: 5 seconds, doubled on each subsequent attempt (5s, 10s, 20s, 40s).
- **Dynamic Header Parsing**: The retry logic intercepts the exception details and searches for provider-specific fields:
  - `retry_after_seconds` (commonly used by Venice API).
  - `retry-after` (standard HTTP rate limit header).
- **Wait Behavior**: If a retry-after duration is found, the agent overrides the exponential delay and sleeps for that exact amount of time (plus a 1-second safety buffer) before retrying.

---

## 4. Local State Files

The application writes state and history locally to the following files in the project root:

- **`.code_assistant_memory.pkl`**: Stores the serialized LangGraph checkpoint data (created by `PersistentMemorySaver`).
- **`.code_assistant_state.json`**: Stores the cooperative pipeline and subtask history managed by the `StateManager`.
