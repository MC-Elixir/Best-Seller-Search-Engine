"""LLM 判断两个商品是否同款。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class JudgeResult:
    same_product: bool
    confidence: float
    reason: str


_SYSTEM = (
    "You are a sourcing analyst. Given an Amazon/Temu product and a 1688 supplier offer, "
    "decide if they are the SAME physical product (ignore language, brand labels and packaging). "
    "Respond in strict JSON with keys: same_product (bool), confidence (0-1 float), reason (short string)."
)


def _build_user_prompt(source_title: str, supplier_title: str, **extra: Any) -> str:
    payload = {
        "source_title": source_title,
        "supplier_title": supplier_title,
        **extra,
    }
    return json.dumps(payload, ensure_ascii=False)


class LLMJudge:
    def __init__(self) -> None:
        self.provider = self._pick_provider()

    @staticmethod
    def _pick_provider() -> str:
        if settings.anthropic_api_key:
            return "anthropic"
        if settings.openai_api_key:
            return "openai"
        return "heuristic"

    def judge(
        self,
        source_title: str,
        supplier_title: str,
        similarity: float,
        **extra: Any,
    ) -> JudgeResult:
        if self.provider == "heuristic":
            return self._heuristic(source_title, supplier_title, similarity)
        try:
            if self.provider == "anthropic":
                return self._call_anthropic(source_title, supplier_title, **extra)
            return self._call_openai(source_title, supplier_title, **extra)
        except Exception as e:  # pragma: no cover
            logger.warning("LLM judge failed (%s), falling back to heuristic", e)
            return self._heuristic(source_title, supplier_title, similarity)

    @staticmethod
    def _heuristic(source_title: str, supplier_title: str, similarity: float) -> JudgeResult:
        same = similarity >= 0.25
        return JudgeResult(
            same_product=same,
            confidence=min(1.0, similarity * 1.5),
            reason=f"heuristic similarity={similarity:.2f}",
        )

    def _call_anthropic(self, source_title: str, supplier_title: str, **extra: Any) -> JudgeResult:  # pragma: no cover
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_user_prompt(source_title, supplier_title, **extra)}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        return self._parse(text)

    def _call_openai(self, source_title: str, supplier_title: str, **extra: Any) -> JudgeResult:  # pragma: no cover
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _build_user_prompt(source_title, supplier_title, **extra)},
            ],
        )
        return self._parse(resp.choices[0].message.content or "")

    @staticmethod
    def _parse(text: str) -> JudgeResult:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return JudgeResult(same_product=False, confidence=0.0, reason=f"unparseable: {text[:120]}")
        return JudgeResult(
            same_product=bool(data.get("same_product", False)),
            confidence=float(data.get("confidence", 0.0)),
            reason=str(data.get("reason", ""))[:500],
        )
