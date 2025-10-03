import sqlite3
import traceback
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import loguru
from loguru._file_sink import FileSink

from simple_kv.lib.kv.kv_db import KvDb
from simple_kv.lib.kv.kv_mgr import KvMgr


class KvDbTest(unittest.TestCase):
    mgr: KvMgr
    db: KvDb
    tmp_dir: TemporaryDirectory

    @classmethod
    def setUpClass(cls) -> None:
        for handler_id, handler in loguru.logger._core.handlers.items():  # type: ignore
            if isinstance(handler._sink, FileSink):
                loguru.logger.remove(handler_id)

    def setUp(self):
        self.tmp_dir = TemporaryDirectory()
        self.mgr = KvMgr(save_dir=Path(self.tmp_dir.name))
        self.db = self.mgr.db("my_db", missing_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_forbidden_attach(self):
        try:
            fp_other = Path(self.tmp_dir.name) / "tmp.sqlite"
            sqlite3.connect(fp_other)
            with self.db.connect() as conn:
                conn.execute(f"ATTACH DATABASE '{fp_other.absolute()}' AS tmp")
        except:
            traceback.print_exc()
            return

        raise Exception()
