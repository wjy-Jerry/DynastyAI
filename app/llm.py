from app.config import Settings


def chat_payload(settings: Settings, system: str, user: str, max_tokens: int) -> dict:
    """Build the shared Chat Completions request without changing the OpenAI contract."""
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    if settings.llm_provider == "openai":
        payload["max_tokens"] = max_tokens
    elif settings.llm_provider == "alibaba":
        # Qwen's non-streaming JSON mode works in non-thinking mode. Do not cap
        # output tokens: a truncated JSON object cannot pass schema validation.
        payload["enable_thinking"] = False
    else:
        from app.storyboard import GenerationError

        raise GenerationError("LLM_PROVIDER must be 'openai' or 'alibaba'.", 503)
    return payload
