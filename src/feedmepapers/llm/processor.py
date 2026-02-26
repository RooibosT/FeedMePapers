"""Local LLM processing via Ollama for Korean translation + novelty extraction."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import ollama as ollama_client

from ..models import Paper

logger = logging.getLogger(__name__)

SYSTEM_MSG = (
    "You are a Korean-language academic assistant. "
    "You MUST write ONLY in Korean (한국어). "
    "NEVER use Chinese characters (汉字/中文). "
    "If you are unsure how to translate a term, keep it in English. "
    "Do NOT add any meta-commentary, explanations, or notes about the translation process."
)

TRANSLATE_PROMPT = """다음 영어 초록을 한국어로 번역하세요.
기술 용어는 영어 그대로 유지하세요 (예: Transformer, attention, SLAM, embodied AI).
반드시 한국어 번역만 출력하세요. 중국어(汉字)를 절대 사용하지 마세요.

Abstract:
{abstract}"""

NOVELTY_PROMPT = """다음 논문 제목과 초록을 읽고, 이 논문의 핵심 novelty를 한국어 2~3문장으로 요약하세요.
핵심: 어떤 새로운 방법이 제안되었는지, 어떤 문제를 해결하는지, 기존 연구 대비 장점이 무엇인지.
반드시 한국어만 출력하세요. 중국어(汉字)를 절대 사용하지 마세요.

Title: {title}
Abstract: {abstract}"""


@dataclass
class LLMConfig:
    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434"
    timeout: int = 180
    temperature: float = 0.3

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def _has_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _strip_chinese_lines(text: str) -> str:
    cleaned = []
    for line in text.split("\n"):
        chinese_chars = len(_CJK_RE.findall(line))
        total_chars = len(line.strip())
        if total_chars > 0 and chinese_chars / total_chars > 0.3:
            continue
        cleaned_line = _CJK_RE.sub("", line)
        cleaned.append(cleaned_line)
    result = "\n".join(cleaned).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def _call_llm(config: LLMConfig, prompt: str, max_retries: int = 2) -> str:
    client = ollama_client.Client(host=config.base_url, timeout=config.timeout)
    messages = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(max_retries + 1):
        try:
            response = client.chat(
                model=config.model,
                messages=messages,
                options={"temperature": config.temperature},
            )
            text = response["message"]["content"].strip()

            if not _has_chinese(text):
                return text

            if attempt < max_retries:
                logger.warning(f"[LLM] Chinese detected (attempt {attempt + 1}), retrying...")
                messages = [
                    {"role": "system", "content": SYSTEM_MSG},
                    {
                        "role": "user",
                        "content": prompt
                        + "\n\n[CRITICAL] 이전 응답에 중국어가 포함되었습니다. 반드시 한국어만 사용하세요!",
                    },
                ]
                continue

            logger.warning("[LLM] Chinese still present after retries, stripping...")
            return _strip_chinese_lines(text)

        except Exception as e:
            logger.error(f"[LLM] Error: {e}")
            return ""

    return ""


MAX_ABSTRACT_CHARS = 3000


def _truncate_abstract(abstract: str) -> str:
    if len(abstract) <= MAX_ABSTRACT_CHARS:
        return abstract
    return abstract[:MAX_ABSTRACT_CHARS] + "..."


def translate_abstract(config: LLMConfig, abstract: str) -> str:
    prompt = TRANSLATE_PROMPT.format(abstract=_truncate_abstract(abstract))
    return _call_llm(config, prompt)


def extract_novelty(config: LLMConfig, title: str, abstract: str) -> str:
    prompt = NOVELTY_PROMPT.format(title=title, abstract=_truncate_abstract(abstract))
    return _call_llm(config, prompt)


def _check_gpu_preflight(config: LLMConfig) -> None:
    """Check if the model is running on GPU. Warn and abort if CPU-only."""
    allow_cpu = os.environ.get("FEEDMEPAPERS_ALLOW_CPU", "").strip() == "1"
    client = ollama_client.Client(host=config.base_url, timeout=config.timeout)

    def _find_model():
        try:
            ps = client.ps()
        except Exception:
            return None
        for m in ps.get("models", []):
            name = m.get("model", "") or m.get("name", "")
            if config.model in name:
                return m
        return None

    target = _find_model()
    if target is None:
        try:
            client.chat(
                model=config.model,
                messages=[{"role": "user", "content": "ping"}],
                options={"temperature": 0, "num_predict": 1},
            )
        except Exception as e:
            logger.error(f"[LLM] Failed to load model '{config.model}': {e}")
            return
        target = _find_model()

    if target is None:
        logger.warning("[LLM] Could not verify GPU/CPU state via ollama ps.")
        return

    size = target.get("size", 0)
    size_vram = target.get("size_vram", 0)

    if size <= 0:
        return

    vram_ratio = size_vram / size
    if vram_ratio >= 0.95:
        logger.info(f"[LLM] {config.model} running on GPU (VRAM: {vram_ratio*100:.0f}%)")
        return

    pct = f"{vram_ratio*100:.0f}%"
    msg = (
        f"[LLM] WARNING: {config.model} is running on CPU (VRAM usage: {pct}).\n"
        "  CPU 추론은 매우 느립니다. 가능한 원인:\n"
        "  - Docker Ollama 컨테이너가 GPU를 점유 중 (docker compose stop ollama)\n"
        "  - Ollama가 GPU 없이 시작됨 (ollama 재시작 필요)\n"
        "  - 모델이 VRAM보다 큼 (더 작은 모델 사용 권장)\n"
        "  해결: 다른 Ollama 프로세스를 종료하고 다시 시도하세요.\n"
        "  CPU 모드를 허용하려면: FEEDMEPAPERS_ALLOW_CPU=1"
    )
    if allow_cpu:
        logger.warning(msg)
    else:
        raise RuntimeError(msg)


def _unload_model(config: LLMConfig) -> None:
    """Send keep_alive=0 to tell Ollama to unload the model and free VRAM."""
    try:
        client = ollama_client.Client(host=config.base_url, timeout=config.timeout)
        client.chat(
            model=config.model,
            messages=[{"role": "user", "content": ""}],
            options={"num_predict": 1},
            keep_alive=0,
        )
        logger.info(f"[LLM] Model '{config.model}' unloaded from VRAM")
    except Exception as e:
        logger.warning(f"[LLM] Failed to unload model: {e}")


def process_papers(config: LLMConfig, papers: list[Paper]) -> list[Paper]:
    _check_gpu_preflight(config)
    total = len(papers)
    for i, paper in enumerate(papers):
        logger.info(f"[LLM] Processing {i + 1}/{total}: {paper.title[:60]}...")

        paper.abstract_ko = translate_abstract(config, paper.abstract)
        paper.novelty_ko = extract_novelty(config, paper.title, paper.abstract)

        if paper.abstract_ko:
            has_cn = _has_chinese(paper.abstract_ko) or _has_chinese(paper.novelty_ko)
            status = "OK" if not has_cn else "OK (some Chinese stripped)"
            logger.info(f"  -> Translation {status} ({len(paper.abstract_ko)} chars)")
        else:
            logger.warning(f"  -> Translation FAILED")

    _unload_model(config)
    return papers
