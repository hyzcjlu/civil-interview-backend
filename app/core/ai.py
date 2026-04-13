"""LLM (Qwen) and ASR utilities"""
import asyncio
import logging
import random
from typing import Optional, Dict

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# OpenAI-compatible client for Qwen
_client: Optional[OpenAI] = None


def get_client() -> Optional[OpenAI]:
    global _client
    if not settings.qwen_api_key:
        return None
    if _client is None:
        _client = OpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=25.0,
        )
    return _client


def call_llm_api(
    prompt: str,
    system_msg: str = "You are a civil service interview expert. Output JSON only.",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> Optional[Dict]:
    """Synchronous LLM call (run via executor to avoid blocking)"""
    import json

    client = get_client()
    if not client:
        logger.warning("No QWEN_API_KEY configured, skipping LLM call")
        return None
    try:
        response = client.chat.completions.create(
            model=settings.qwen_model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=25.0,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return json.loads(content.strip())
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


async def call_llm_api_async(
    prompt: str,
    system_msg: str = "You are a civil service interview expert. Output JSON only.",
    temperature: float = 0.1,
    max_tokens: int = 2000,
) -> Optional[Dict]:
    """Async wrapper to avoid blocking the event loop"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: call_llm_api(prompt, system_msg, temperature, max_tokens)
    )


async def transcribe_audio_file(audio_bytes: bytes) -> str:
    """Simulate ASR — returns realistic mock transcript"""
    mock_answers = [
        "针对这个问题，我认为首先需要从整体上把握，然后具体分析。第一，要充分了解实际情况，深入调查研究。第二，要结合相关政策规定，制定切实可行的方案。第三，要加强沟通协调，确保各方配合。最后，要注重总结经验，持续改进完善。",
        "我觉得解决这个问题需要从三个方面着手：一是加强顶层设计，明确目标方向；二是完善制度建设，提供制度保障；三是强化落实执行，确保取得实效。在具体操作中，还需要注重细节，防范风险，确保工作稳步推进。",
        "对于这道题，我的思路是：首先明确问题的核心所在，其次分析产生问题的原因，然后提出针对性的解决措施，最后考虑可能的风险和应对策略。总体来说，要坚持实事求是、因地制宜的原则，不能搞一刀切。",
    ]
    if len(audio_bytes) < 100:
        return "（录音内容较短，未能有效转录）"
    return random.choice(mock_answers)


# Province name mapping
PROVINCE_NAMES = {
    "national": "国家公务员考试",
    "beijing": "北京",
    "guangdong": "广东",
    "zhejiang": "浙江",
    "sichuan": "四川",
    "jiangsu": "江苏",
    "henan": "河南",
    "shandong": "山东",
    "hubei": "湖北",
    "hunan": "湖南",
    "liaoning": "辽宁",
    "shanxi": "陕西",
}

DIMENSION_NAMES = {
    "analysis": "综合分析",
    "practical": "实务落地",
    "emergency": "应急应变",
    "legal": "法治思维",
    "logic": "逻辑结构",
    "expression": "语言表达",
}

POSITION_NAMES = {
    "tax": "税务系统",
    "customs": "海关系统",
    "police": "公安系统",
    "court": "法院系统",
    "procurate": "检察系统",
    "market": "市场监管",
    "general": "综合管理",
    "township": "乡镇基层",
    "finance": "银保监会",
    "diplomacy": "外交系统",
}
