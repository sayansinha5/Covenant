import os
import time
import uuid


def uuid7() -> str:
    """RFC 9562 UUIDv7: 48-bit Unix milliseconds, then random bits. Time-ordered, safe to expose."""
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= ((rand >> 62) & 0xFFF) << 64  # rand_a, 12 bits
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # rand_b, 62 bits
    return str(uuid.UUID(int=value))


def new_request_id() -> str:
    return uuid.uuid4().hex
