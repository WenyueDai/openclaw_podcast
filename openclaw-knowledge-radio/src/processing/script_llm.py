from __future__ import annotations

import os
from typing import Any, Dict, List

from openai import OpenAI


SYSTEM_PROMPT = """你是一个严谨但好听的“每日知识播客”编辑与主持人。
目标：把今天的新内容编排成约 60 分钟的中文播客脚本，信息密度高，但不要像论文朗读。
硬性要求：
- 必须保留每条内容的来源链接（原样输出 URL）。
- 不要编造不存在的细节或结论；如果信息不足，用“文章摘要未提供更多细节”。
- 节目结构固定为：
  1) 开场（1-2分钟）：今天主题概览
  2) Innovation & Protein Design（约 35-40分钟）：挑选最重要的 10-15 条，每条 2-4 句（核心点+为什么重要+下一步/实验验证提示）
  3) Daily knowledge（约 8-10分钟）：1-2 条轻松但有营养的知识
  4) Deep Dive（约 8-12分钟）：从今天内容里选 1 条最值得深挖的，讲清背景、关键点、争议/不确定性、以及“可验证预测”
  5) 结尾（1-2分钟）：今天回顾 + 明日预告（1句） + 来源清单（列出所有引用过的条目标题+URL）
- 输出必须可直接拿去 TTS 朗读，不要输出 JSON，不要输出 markdown 表格。
风格：
- 口语化但不油腻；句子别太长；适合跑步时听。
"""


def _client_from_config(cfg: Dict[str, Any]) -> OpenAI:
    api_key_env = cfg.get("llm", {}).get("api_key_env", "OPENROUTER_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {api_key_env} for OpenRouter API key")

    # OpenRouter is OpenAI-compatible
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def build_podcast_script_llm(*, date_str: str, items: List[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    client = _client_from_config(cfg)
    model = cfg["llm"]["model"]
    temperature = float(cfg["llm"].get("temperature", 0.25))
    max_tokens = int(cfg["llm"].get("max_output_tokens", 5200))

    # Compact input to avoid huge prompts
    lines: List[str] = []
    lines.append(f"DATE: {date_str}")
    lines.append("TODAY_ITEMS (title/url/source/snippet only):")
    for i, it in enumerate(items, start=1):
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        src = (it.get("source") or "").strip()
        bucket = (it.get("bucket") or "").strip()
        snippet = (it.get("one_liner") or "").strip()
        if len(snippet) > 420:
            snippet = snippet[:417] + "..."
        lines.append(f"{i}. [{bucket}] {title}")
        lines.append(f"   source: {src}")
        lines.append(f"   url: {url}")
        if snippet:
            lines.append(f"   snippet: {snippet}")

    user_prompt = (
        "请只基于 TODAY_ITEMS 生成播客脚本。"
        "不要引入外部信息，不要捏造论文结论。

" + "\n".join(lines)
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    out = resp.choices[0].message.content or ""
    return out.strip()
