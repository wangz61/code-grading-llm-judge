"""Completion function for OpenAI Evals that sends any model name to the chat endpoint.

Evals sends model names it does not know (such as gpt-4.1) to the legacy completions endpoint, and the built-in
OpenAIChatCompletionFn cannot be used from the registry because the registry passes it a `registry` argument.
"""
from evals.completion_fns.openai import OpenAIChatCompletionFn


class ChatCompletionFn(OpenAIChatCompletionFn):
    def __init__(self, model: str, registry=None, **kwargs):
        super().__init__(model=model, **kwargs)


def _patch_token_usage() -> None:
    """oaieval sums every usage field, but newer openai SDKs include nested *_details objects, which crash the sum.

    Replace the summary with one that only adds the integer counters. Grading results are unaffected.
    """
    import evals.cli.oaieval as cli

    def add_token_usage_to_result(result, recorder):
        totals: dict[str, int] = {}
        for event in recorder.get_events("sampling"):
            for key, value in dict(event.data.get("usage") or {}).items():
                if isinstance(value, int):
                    totals[key] = totals.get(key, 0) + value
        for key, value in totals.items():
            result[f"usage_{key}"] = value

    cli.add_token_usage_to_result = add_token_usage_to_result


_patch_token_usage()
