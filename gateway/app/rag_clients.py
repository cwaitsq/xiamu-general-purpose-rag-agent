from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings


class HttpJsonError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> Any:
    body = None
    merged_headers = {"Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=body, headers=merged_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HttpJsonError(f"HTTP {exc.code}: {detail or exc.reason}", status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise HttpJsonError(f"network_error: {exc.reason}") from exc


ROOT = Path(__file__).resolve().parents[2]


@dataclass
class QmdSearchHit:
    docid: str
    score: float
    file: str
    line: int
    title: str
    snippet: str
    body: str = ""
    context: str = ""


class EmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.embedding_api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.is_configured():
            raise HttpJsonError("embedding_api_key_not_configured")
        payload: dict[str, Any] = {
            "model": self.settings.embedding_model,
            "input": texts,
            "encoding_format": "float",
        }
        if self.settings.embedding_dimensions:
            payload["dimensions"] = self.settings.embedding_dimensions
        data = _request_json(
            "POST",
            f"{self.settings.embedding_base_url}/embeddings",
            payload=payload,
            headers={"Authorization": f"Bearer {self.settings.embedding_api_key}"},
            timeout=self.settings.qdrant_timeout_seconds,
        )
        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in items]


class OpenAICompatibleChatClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return bool(self.settings.llm_enabled and self.settings.llm_api_key and self.settings.llm_model)

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if not self.is_configured():
            raise HttpJsonError("llm_not_configured")
        payload = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = _request_json(
            "POST",
            f"{self.settings.llm_base_url}/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            timeout=self.settings.qdrant_timeout_seconds,
        )
        choices = data.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(str(item.get("text", "")).strip())
            return "\n".join(text for text in texts if text).strip()
        return ""


class QmdClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _resolve_base_command(self) -> list[str]:
        if self.settings.qmd_command:
            return shlex.split(self.settings.qmd_command, posix=os.name != "nt")
        if self.settings.qmd_cli_path:
            return [self.settings.qmd_node_bin, self.settings.qmd_cli_path]
        qmd_bin = shutil.which("qmd")
        if qmd_bin:
            return [qmd_bin]
        return []

    def is_configured(self) -> bool:
        return bool(self._resolve_base_command()) and bool(self.settings.qmd_collection)

    def command_display(self) -> str:
        return " ".join(self._resolve_base_command())

    def collection_exists(self, name: str | None = None) -> bool:
        if not self.is_configured():
            return False
        output = self._run(["collection", "list"])
        target_name = name or self.settings.qmd_collection
        return target_name in output

    def init_index(self) -> None:
        self._run(["init"])

    def add_collection(self, path: str, name: str) -> None:
        self._run(["collection", "add", path, "--name", name])

    def update(self) -> None:
        self._run(["update"])

    def search(self, *, query: str, limit: int, min_score: float, collections: list[str] | None = None) -> list[QmdSearchHit]:
        if not self.is_configured():
            raise HttpJsonError("qmd_not_configured")

        collection_names = collections or [self.settings.qmd_collection]
        collection_args: list[str] = []
        for name in collection_names:
            collection_args.extend(["-c", name])

        command_name = "query" if self.settings.qmd_search_mode == "query" else "search"
        args = [command_name, query, "--json", "-n", str(limit), "--min-score", str(min_score), *collection_args]
        if command_name == "query":
            args.extend(["--no-rerank", "--no-gpu"])

        raw = self._run(args)
        data = json.loads(raw or "[]")
        if not isinstance(data, list):
            return []

        hits: list[QmdSearchHit] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            hits.append(
                QmdSearchHit(
                    docid=str(item.get("docid", "")).lstrip("#"),
                    score=float(item.get("score", 0.0)),
                    file=str(item.get("file", "")),
                    line=int(item.get("line", 0) or 0),
                    title=str(item.get("title", "")),
                    snippet=str(item.get("snippet", "")),
                    body=str(item.get("body", "")),
                    context=str(item.get("context", "")),
                )
            )
        return hits

    def _run(self, args: list[str]) -> str:
        base_command = self._resolve_base_command()
        if not base_command:
            raise HttpJsonError("qmd_command_not_found")

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        env.setdefault("CI", "1")
        try:
            result = subprocess.run(
                [*base_command, *args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.settings.qmd_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise HttpJsonError("qmd_timeout") from exc
        except OSError as exc:
            raise HttpJsonError(f"qmd_launch_failed: {exc}") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise HttpJsonError(f"qmd_command_failed: {detail or f'exit_{result.returncode}'}", status_code=result.returncode)

        return result.stdout.strip()


class QdrantClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.qdrant_api_key:
            headers["api-key"] = self.settings.qdrant_api_key
        return headers

    def collection_exists(self) -> bool:
        try:
            _request_json(
                "GET",
                f"{self.settings.qdrant_url}/collections/{self.settings.qdrant_collection}",
                headers=self._headers(),
                timeout=self.settings.qdrant_timeout_seconds,
            )
            return True
        except HttpJsonError as exc:
            if exc.status_code == 404:
                return False
            raise

    def ensure_collection(self, vector_size: int) -> None:
        if self.collection_exists():
            return
        payload = {
            "vectors": {
                "size": vector_size,
                "distance": self.settings.qdrant_distance,
            }
        }
        _request_json(
            "PUT",
            f"{self.settings.qdrant_url}/collections/{self.settings.qdrant_collection}",
            payload=payload,
            headers=self._headers(),
            timeout=self.settings.qdrant_timeout_seconds,
        )

    def upsert_points(self, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        _request_json(
            "PUT",
            f"{self.settings.qdrant_url}/collections/{self.settings.qdrant_collection}/points?wait=true",
            payload={"points": points},
            headers=self._headers(),
            timeout=self.settings.qdrant_timeout_seconds,
        )

    def search(
        self,
        *,
        vector: list[float],
        limit: int,
        query_filter: dict[str, Any] | None,
        score_threshold: float | None,
    ) -> list[dict[str, Any]]:
        common_payload = {
            "limit": limit,
            "with_payload": True,
        }
        if query_filter:
            common_payload["filter"] = query_filter
        if score_threshold is not None:
            common_payload["score_threshold"] = score_threshold

        try:
            data = _request_json(
                "POST",
                f"{self.settings.qdrant_url}/collections/{self.settings.qdrant_collection}/points/query",
                payload={**common_payload, "query": vector},
                headers=self._headers(),
                timeout=self.settings.qdrant_timeout_seconds,
            )
            result = data.get("result", {})
            if isinstance(result, dict):
                return result.get("points", [])
            if isinstance(result, list):
                return result
            return []
        except HttpJsonError as exc:
            if exc.status_code not in {404, 405}:
                raise

        data = _request_json(
            "POST",
            f"{self.settings.qdrant_url}/collections/{self.settings.qdrant_collection}/points/search",
            payload={**common_payload, "vector": vector},
            headers=self._headers(),
            timeout=self.settings.qdrant_timeout_seconds,
        )
        result = data.get("result", [])
        return result if isinstance(result, list) else []
