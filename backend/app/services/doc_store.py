"""文档存储（MongoDB）。

保存：PRD 原文、需求解析结果、代码版本、审查报告、修正记录、评估报告。
DOC_STORE_BACKEND=auto 时，MongoDB 不可达自动降级为本地 JSON 存储。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("webmind.docstore")


class MemoryDocStore:
    """本地降级实现：按集合存 JSON 文件。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                self._data = {}

    def _flush(self) -> None:
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def insert(self, collection: str, doc: dict) -> str:
        with self._lock:
            doc = dict(doc)
            doc.setdefault("_id", f"{int(time.time() * 1000)}-{len(self._data.get(collection, []))}")
            self._data.setdefault(collection, []).append(doc)
            self._flush()
            return str(doc["_id"])

    def find(self, collection: str, query: dict | None = None, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._data.get(collection, [])
            if query:
                rows = [r for r in rows if all(r.get(k) == v for k, v in query.items())]
            return [dict(r) for r in rows[-limit:]]

    def find_one(self, collection: str, query: dict, sort_key: str | None = None) -> dict | None:
        rows = self.find(collection, query, limit=1000)
        if not rows:
            return None
        if sort_key:
            rows.sort(key=lambda r: r.get(sort_key, 0))
        return rows[-1]

    def delete(self, collection: str, query: dict) -> int:
        with self._lock:
            rows = self._data.get(collection, [])
            keep = [r for r in rows if not all(r.get(k) == v for k, v in query.items())]
            removed = len(rows) - len(keep)
            self._data[collection] = keep
            self._flush()
            return removed


class MongoDocStore(MemoryDocStore):
    """MongoDB 实现，连接失败时回退到父类逻辑。"""

    def __init__(self, path: Path):
        super().__init__(path)
        import pymongo  # 局部导入，未安装也不影响降级

        url = settings.MONGO_URL or f"mongodb://{settings.MONGO_HOST}:{settings.MONGO_PORT}"
        self.client = pymongo.MongoClient(url, serverSelectionTimeoutMS=1500)
        self.client.admin.command("ping")
        self.db = self.client[settings.MONGO_DATABASE]

    def insert(self, collection: str, doc: dict) -> str:
        doc = dict(doc)
        doc.pop("_id", None)
        result = self.db[collection].insert_one(doc)
        return str(result.inserted_id)

    def find(self, collection: str, query: dict | None = None, limit: int = 100) -> list[dict]:
        cursor = self.db[collection].find(query or {}).sort("_id", -1).limit(limit)
        return [self._clean(d) for d in cursor]

    @staticmethod
    def _clean(doc: dict) -> dict:
        doc = dict(doc)
        doc["_id"] = str(doc.get("_id"))
        return doc


_store: MemoryDocStore | None = None
_lock = threading.Lock()


def get_doc_store() -> MemoryDocStore:
    global _store
    if _store is not None:
        return _store
    with _lock:
        if _store is not None:
            return _store
        fallback_path = settings.resolve_file("./data/doc_store.json")
        backend = (settings.DOC_STORE_BACKEND or "auto").lower()
        store: MemoryDocStore
        if backend == "mongo":
            store = MongoDocStore(fallback_path)
            logger.info("文档存储: MongoDB(%s)", settings.MONGO_HOST)
        elif backend == "memory":
            store = MemoryDocStore(fallback_path)
        else:
            try:
                store = MongoDocStore(fallback_path)
                logger.info("文档存储: MongoDB(%s)", settings.MONGO_HOST)
            except Exception as exc:  # noqa: BLE001
                logger.warning("MongoDB 不可用(%s)，降级为本地 JSON 存储", exc)
                store = MemoryDocStore(fallback_path)
        _store = store
        return _store


def insert(collection: str, doc: dict) -> str:
    return get_doc_store().insert(collection, doc)


def find(collection: str, query: dict | None = None, limit: int = 100) -> list[dict]:
    return get_doc_store().find(collection, query, limit)


def find_one(collection: str, query: dict, sort_key: str | None = None) -> dict | None:
    return get_doc_store().find_one(collection, query, sort_key)


def list_collections() -> Iterable[str]:
    return ["requirements", "code_versions", "review_reports", "feedback_records", "evaluation_reports"]
