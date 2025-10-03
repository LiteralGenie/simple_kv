import re
from dataclasses import dataclass


@dataclass
class KvIdentifier:
    text: str

    def __str__(self):
        raise NotImplementedError()

    @staticmethod
    def validate(raw: str) -> "KvIdentifier":
        m = re.search(r"[^a-z_]", raw, re.IGNORECASE)
        if m:
            raise Exception(f"Invalid identifier: {raw}")

        return KvIdentifier(raw)
