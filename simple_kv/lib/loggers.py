import loguru

from simple_kv.lib.paths import LOG_DIR

loguru.logger.add(
    LOG_DIR / "kv_db.log",
    filter=lambda record: record["extra"].get("name") == "kv_db",
    rotation="10 MB",
    retention=2,
)
KV_LOG = loguru.logger.bind(name="kv_db")
