"""RAG 组件知识库检索。

流程：组件文档 → 切片 → 打分检索 → 注入 Prompt → 代码生成 → 组件白名单校验
对应文档：WebMind完整开发指导.md 第 10 节 / WebMind项目全景设计.md 5.2
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.services import cache

logger = get_logger("webmind.rag")


@dataclass
class Chunk:
    component: str
    title: str
    content: str
    source: str
    tags: list[str] = field(default_factory=list)


_TOKEN_RE = re.compile(r"[A-Za-z0-9\-_\.]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    result: list[str] = []
    # 中文按 2-gram 补 token，提升中文查询召回
    for token in tokens:
        result.append(token)
    cjk = "".join(t for t in tokens if "\u4e00" <= t <= "\u9fff")
    for i in range(len(cjk) - 1):
        result.append(cjk[i : i + 2])
    return result


class ComponentRetriever:
    """组件文档检索器（关键词 + 标签加权，热点结果进 Redis 缓存）。"""

    def __init__(self, docs_dir: Path | None = None):
        self.docs_dir = docs_dir or settings.knowledge_dir
        self._chunks: list[Chunk] = []
        self.load()

    # ---------------- 文档加载 ----------------
    def load(self) -> None:
        self._chunks = []
        if not self.docs_dir.exists():
            logger.warning("组件知识库目录不存在: %s", self.docs_dir)
            return
        for path in sorted(self.docs_dir.glob("*.md")):
            self._chunks.extend(self._parse_file(path))
        logger.info("组件知识库加载完成：%s 个切片", len(self._chunks))

    def _parse_file(self, path: Path) -> list[Chunk]:
        text = path.read_text(encoding="utf-8")
        chunks: list[Chunk] = []
        current_title = path.stem
        current_component = ""
        buffer: list[str] = []
        tags: list[str] = []

        for line in text.splitlines():
            if line.startswith("## "):
                if buffer:
                    chunks.append(
                        Chunk(
                            component=current_component,
                            title=current_title,
                            content="\n".join(buffer).strip(),
                            source=path.name,
                            tags=list(tags),
                        )
                    )
                buffer = []
                heading = line[3:].strip()
                current_title = heading
                match = re.search(r"(el-[a-z\-]+|wm-[a-z\-]+|uni\.[a-zA-Z]+)", heading)
                current_component = match.group(1) if match else heading
                tags = _tokenize(heading)
            else:
                buffer.append(line)
        if buffer:
            chunks.append(
                Chunk(
                    component=current_component,
                    title=current_title,
                    content="\n".join(buffer).strip(),
                    source=path.name,
                    tags=list(tags),
                )
            )
        return chunks

    # ---------------- 检索 ----------------
    def search(self, query: str, top_k: int = 4) -> list[dict]:
        cache_key = f"rag:{query}:{top_k}"
        cached = cache.cache_get(cache_key)
        if cached is not None:
            return cached

        query_tokens = set(_tokenize(query))
        scored: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            content_tokens = _tokenize(chunk.content + " " + chunk.title)
            overlap = query_tokens.intersection(set(content_tokens))
            tag_hit = query_tokens.intersection(set(chunk.tags))
            score = len(overlap) + len(tag_hit) * 3
            if chunk.component and chunk.component in query:
                score += 10
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = [
            {
                "component": chunk.component,
                "title": chunk.title,
                "content": chunk.content[:1200],
                "source": chunk.source,
                "score": round(score, 2),
            }
            for score, chunk in scored[:top_k]
        ]
        cache.cache_set(cache_key, results, ttl=1800)
        return results

    # ---------------- 白名单 ----------------
    def whitelist(self) -> set[str]:
        """组件白名单：只允许使用知识库中真实存在的组件。"""
        cached = cache.cache_get("rag:whitelist")
        if cached:
            return set(cached)
        names = {c.component for c in self._chunks if re.match(r"^(el-|wm-)", c.component)}
        if not names:
            names = {"el-table", "el-form", "el-button", "el-input", "el-dialog"}
        cache.cache_set("rag:whitelist", sorted(names), ttl=3600)
        return names

    def validate_components(self, code: str) -> list[str]:
        """校验代码中出现的组件是否都在白名单内。"""
        used = set(re.findall(r"<(el-[a-z\-]+|wm-[a-z\-]+)", code))
        allowed = self.whitelist()
        return sorted(used - allowed)


_retriever: ComponentRetriever | None = None


def get_retriever() -> ComponentRetriever:
    global _retriever
    if _retriever is None:
        _retriever = ComponentRetriever()
    return _retriever
