"""FAL image-generation provider (Flux, Recraft, Ideogram, …).

FAL exposes dozens of community-hosted image models under a uniform
queue API. We default to flux-schnell (fast + free-tier-friendly);
agents can pass ``model="fal-ai/flux/dev"`` or any other route.

Docs: https://docs.fal.ai/model-endpoints/
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from ..registry import GeneratedImage


QUEUE_BASE = "https://queue.fal.run"
TIMEOUT = 120.0
POLL_INTERVAL = 1.5
DEFAULT_MODEL = "fal-ai/flux/schnell"


@dataclass
class FalProvider:
    name: str = "fal"
    priority: int = 70
    requires_env: tuple = ("FAL_KEY",)
    supported_models: list[str] = field(default_factory=lambda: [
        "fal-ai/flux/schnell",
        "fal-ai/flux/dev",
        "fal-ai/flux-pro",
        "fal-ai/ideogram/v2",
        "fal-ai/recraft-v3",
    ])

    def is_available(self) -> bool:
        return bool(os.environ.get("FAL_KEY"))

    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        size: str = "1024x1024",
        n: int = 1,
    ) -> list[GeneratedImage]:
        key = os.environ.get("FAL_KEY", "")
        if not key:
            raise RuntimeError("FAL_KEY not set")
        mdl = model or DEFAULT_MODEL
        w, h = _parse_size(size)
        payload = {
            "prompt": prompt,
            "image_size": {"width": w, "height": h},
            "num_images": max(1, min(int(n), 4)),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Key {key}",
        }

        # Queue submit → poll until completed → fetch response
        submit_req = urllib.request.Request(
            f"{QUEUE_BASE}/{mdl}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(submit_req, timeout=TIMEOUT) as resp:
                submit = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = str(e)
            raise RuntimeError(f"FAL submit HTTP {e.code}: {body}") from e

        status_url = submit.get("status_url")
        response_url = submit.get("response_url")
        if not status_url or not response_url:
            raise RuntimeError(f"FAL response missing queue URLs: {submit}")

        # Poll
        deadline = time.time() + TIMEOUT
        while time.time() < deadline:
            time.sleep(POLL_INTERVAL)
            status_req = urllib.request.Request(status_url, headers=headers)
            try:
                with urllib.request.urlopen(status_req, timeout=30) as sr:
                    status = json.loads(sr.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"FAL status HTTP {e.code}") from e
            st = status.get("status")
            if st == "COMPLETED":
                break
            if st in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"FAL job {st}: {status}")
        else:
            raise RuntimeError("FAL job timed out")

        # Fetch final result
        result_req = urllib.request.Request(response_url, headers=headers)
        with urllib.request.urlopen(result_req, timeout=TIMEOUT) as rr:
            result = json.loads(rr.read().decode("utf-8"))

        out: list[GeneratedImage] = []
        for img in result.get("images", []):
            url = str(img.get("url") or "")
            if not url:
                continue
            out.append(GeneratedImage(
                url=url,
                mime=str(img.get("content_type", "image/png")),
                revised_prompt=prompt,
                extras={"model": mdl, "width": img.get("width"), "height": img.get("height")},
            ))
        return out


def _parse_size(size: str) -> tuple[int, int]:
    try:
        w, h = size.lower().split("x")
        return max(256, int(w)), max(256, int(h))
    except Exception:
        return 1024, 1024
