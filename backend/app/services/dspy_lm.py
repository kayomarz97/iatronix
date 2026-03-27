import dspy


def get_dspy_lm(model_id: str, api_key: str, provider: str = "anthropic") -> dspy.LM:
    prefix = "anthropic" if provider == "anthropic" else "openai"
    return dspy.LM(f"{prefix}/{model_id}", api_key=api_key, max_tokens=4096)
