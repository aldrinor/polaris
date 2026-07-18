# -*- coding: utf-8 -*-
"""
DRB-II transport ADAPTER (disclosed transport swap).

The official DRB-II repo ships a `gemini_client.py` that POSTs a Gemini-native payload
(Bearer token + `rock-request-id`) to an internal proxy `GEMINI_API_URL`. That proxy is
NOT reachable in this environment, and the provided Google AI Studio key is dead
("reported as leaked", HTTP 403). To run the OFFICIAL scorer (`run_evaluation.py` +
`aggregate_scores.py`, both byte-identical to upstream @11d87de) we swap ONLY the transport:
this module routes the SAME judge (google/gemini-2.5-pro) through OpenRouter's
OpenAI-compatible Chat Completions endpoint.

What is UNCHANGED (the scoring logic): the prompt template, the three-way (1/0/-1) rubric
grading, the blocked-reference semantics, JSON validation/parsing, per-dimension bucketing,
and the pooled aggregation — all live in run_evaluation.py / aggregate_scores.py, which are
the official files. Only the bytes-on-the-wire path changes here.

Interface preserved exactly as the harness imports it:
  GeminiInput, GeminiOutput, GeminiClient, get_config
GeminiOutput.usage_metadata uses the upstream key names (promptTokenCount / candidatesTokenCount
/ thoughtsTokenCount / totalTokenCount) so the harness's token logging keeps working.
"""

import os
import base64
import mimetypes
import requests
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path


def _load_env_file(env_path: str = ".env") -> Dict[str, str]:
    env_vars = {}
    possible_paths = [env_path, os.path.join(os.getcwd(), env_path),
                      os.path.join(Path(__file__).parent, env_path)]
    env_file = None
    for path in possible_paths:
        if os.path.exists(path):
            env_file = path
            break
    if not env_file:
        return env_vars
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        print(f"[warn] failed to read .env file: {e}")
    return env_vars


_ENV_CONFIG = _load_env_file()


def get_config(key: str, default: str = None) -> str:
    value = os.environ.get(key)
    if value:
        return value
    value = _ENV_CONFIG.get(key)
    if value:
        return value
    return default


@dataclass
class GeminiInput:
    text: str
    file_path: Optional[str] = None
    extra_images: Optional[List[Tuple[str, bytes]]] = None
    stream: bool = False


@dataclass
class GeminiOutput:
    text: str
    usage_metadata: Dict = field(default_factory=dict)
    upload_stats: Dict = field(default_factory=dict)
    raw_response: Dict = field(default_factory=dict)


class GeminiClient:
    """Transport adapter -> OpenRouter OpenAI-compatible chat/completions."""

    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None,
                 model: Optional[str] = None, request_id: Optional[str] = None,
                 verbose: bool = True):
        # api_url/token/model come from CLI (--api_url/--token/--model) or env.
        self.api_url = api_url or get_config("GEMINI_API_URL") or \
            "https://openrouter.ai/api/v1/chat/completions"
        self.api_token = api_token or get_config("OPENROUTER_API_KEY") or get_config("GEMINI_API_TOKEN")
        self.model = model or get_config("DRBII_JUDGE_MODEL") or "google/gemini-2.5-pro"
        self.request_id = request_id or get_config("GEMINI_REQUEST_ID", "drbii")
        self.verbose = verbose
        # generous output budget: gemini-2.5-pro spends reasoning tokens before the JSON body;
        # a 50-item batch JSON is large. Keep high so the answer is never truncated.
        self.max_tokens = int(get_config("DRBII_MAX_TOKENS", "32000"))
        if not self.api_token:
            raise ValueError("Missing configuration: OPENROUTER_API_KEY / api token.")
        if not self.model:
            raise ValueError("Missing configuration: judge model.")

    def query(self, input_data: GeminiInput) -> GeminiOutput:
        content_parts: List[Dict] = [{"type": "text", "text": input_data.text}]

        # Attach a main file inline if present (PDF/image). Our .md reports are text-only,
        # so this path is generally unused, but preserved for parity with the upstream client.
        def _inline_image(mime: str, data_b64: str):
            content_parts.append({"type": "image_url",
                                  "image_url": {"url": f"data:{mime};base64,{data_b64}"}})

        if input_data.file_path:
            mime, _ = mimetypes.guess_type(input_data.file_path)
            mime = mime or "application/octet-stream"
            if mime.startswith("image/"):
                with open(input_data.file_path, "rb") as f:
                    _inline_image(mime, base64.b64encode(f.read()).decode("utf-8"))
            elif mime == "application/pdf":
                with open(input_data.file_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                content_parts.append({"type": "file", "file": {
                    "filename": os.path.basename(input_data.file_path),
                    "file_data": f"data:application/pdf;base64,{b64}"}})
        if input_data.extra_images:
            for mime_type, img_bytes in input_data.extra_images:
                _inline_image(mime_type, base64.b64encode(img_bytes).decode("utf-8"))

        # If only text, send a plain string content (simplest, most compatible).
        if len(content_parts) == 1:
            message_content = input_data.text
        else:
            message_content = content_parts

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://polaris.local/drbii",
            "X-Title": "DRB-II official rubric judge",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message_content}],
            "max_tokens": self.max_tokens,
            "temperature": 0,
        }

        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=600)
        if resp.status_code >= 400:
            body = resp.text[:1000] if hasattr(resp, "text") else "?"
            print(f"[err] HTTP {resp.status_code} body: {body}")
            resp.raise_for_status()
        resp_json = resp.json()

        # Surface upstream errors that arrive with HTTP 200 (OpenRouter convention).
        if "error" in resp_json and not resp_json.get("choices"):
            raise RuntimeError(f"judge error: {str(resp_json.get('error'))[:300]}")

        text_content = ""
        choices = resp_json.get("choices") or []
        if choices:
            msg = choices[0].get("message", {}) or {}
            text_content = msg.get("content") or ""

        u = resp_json.get("usage", {}) or {}
        reasoning = 0
        ctd = u.get("completion_tokens_details") or {}
        if isinstance(ctd, dict):
            reasoning = ctd.get("reasoning_tokens", 0) or 0
        usage_metadata = {
            "promptTokenCount": u.get("prompt_tokens", 0),
            "candidatesTokenCount": u.get("completion_tokens", 0),
            "thoughtsTokenCount": reasoning,
            "totalTokenCount": u.get("total_tokens", 0),
        }
        return GeminiOutput(text=text_content, usage_metadata=usage_metadata,
                            upload_stats={"text_segments": 1, "files": []},
                            raw_response=resp_json)
