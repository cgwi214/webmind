"""WebMind 全局配置。

所有配置统一从项目根目录的 .env 读取（见 WebMind环境配置与服务部署指南.md 第 6 节）。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _locate_env_file() -> Path:
    """向上查找项目根目录的 .env 文件。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    # 未找到 .env 时，按源码位置回退到项目根目录，
    # 保证 PROJECT_ROOT 不随当前工作目录变化（否则 data/、evaluation_dataset/ 会解析错位置）。
    project_root = here.parents[3] if len(here.parents) > 3 else here.parent
    return project_root / ".env"


ENV_FILE = _locate_env_file()
PROJECT_ROOT = ENV_FILE.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===================== Application =====================
    APP_NAME: str = "WebMind"
    ENV: str = "development"
    DEBUG: bool = True

    # ===================== Backend =====================
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # ===================== LLM =====================
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    MODEL_NAME: str = "gpt-4.1"
    LLM_MOCK_MODE: str = "auto"  # auto | true | false
    LLM_TIMEOUT: int = 120
    # 视觉评估用的多模态模型（留空则使用结构化降级实现）
    VISION_MODEL: str = ""

    # ===================== MySQL =====================
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = "webmind"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "password"

    # ===================== MongoDB =====================
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_DATABASE: str = "webmind"
    MONGO_URL: str = "mongodb://localhost:27017"

    # ===================== Redis =====================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_URL: str = "redis://localhost:6379"

    # ===================== 降级策略 =====================
    DB_BACKEND: str = "auto"  # auto | mysql | sqlite
    DOC_STORE_BACKEND: str = "auto"  # auto | mongo | memory
    CACHE_BACKEND: str = "auto"  # auto | redis | memory
    SQLITE_PATH: str = "./data/webmind.db"

    # ===================== LangGraph =====================
    LANGGRAPH_CHECKPOINT: bool = True
    MAX_SELF_REPAIR: int = 2

    # ===================== 文件存储 =====================
    UPLOAD_DIR: str = "./data/uploads"
    CODE_OUTPUT_DIR: str = "./data/generated_code"

    # ===================== 代码审查 =====================
    # true 时在生成目录真实执行 npm install && npm run build（耗时较长）
    RUN_REAL_BUILD: bool = False

    # ===================== 评估体系 =====================
    EVALUATION_ENABLED: bool = True
    EVALUATION_DATASET_DIR: str = "./evaluation_dataset"
    EVALUATION_OUTPUT_DIR: str = "./data/evaluation"
    EVAL_HARD_GATE: bool = True
    WEIGHT_CODE: float = 0.30
    WEIGHT_VISUAL: float = 0.25
    WEIGHT_REQUIREMENT: float = 0.20
    WEIGHT_AGENT: float = 0.15
    WEIGHT_ENGINEERING: float = 0.10
    VISUAL_MODEL_WEIGHT: float = 0.7
    VISUAL_HUMAN_WEIGHT: float = 0.3

    # Agent 置信度阈值：低于该值转人工澄清
    REQUIREMENT_CONFIDENCE_THRESHOLD: float = 0.6

    # ===================== 路径工具 =====================
    def resolve(self, path_str: str) -> Path:
        """把相对路径解析到项目根目录之下。"""
        path = Path(path_str)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_file(self, path_str: str) -> Path:
        """解析文件路径（只创建父目录，避免把文件本身建成目录）。"""
        path = Path(path_str)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def upload_dir(self) -> Path:
        return self.resolve(self.UPLOAD_DIR)

    @property
    def code_output_dir(self) -> Path:
        return self.resolve(self.CODE_OUTPUT_DIR)

    @property
    def log_dir(self) -> Path:
        return self.resolve("./logs")

    @property
    def knowledge_dir(self) -> Path:
        return self.resolve("./knowledge/component_docs")

    @property
    def evaluation_dataset_dir(self) -> Path:
        return self.resolve(self.EVALUATION_DATASET_DIR)

    @property
    def evaluation_output_dir(self) -> Path:
        return self.resolve(self.EVALUATION_OUTPUT_DIR)

    @property
    def weights(self) -> dict[str, float]:
        return {
            "code": self.WEIGHT_CODE,
            "visual": self.WEIGHT_VISUAL,
            "requirement": self.WEIGHT_REQUIREMENT,
            "agent": self.WEIGHT_AGENT,
            "engineering": self.WEIGHT_ENGINEERING,
        }


settings = Settings()
