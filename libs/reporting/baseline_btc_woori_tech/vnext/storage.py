"""Atomic immutable evidence publication and disposable report projections."""
import hashlib
import json
import os
import tempfile
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, default=str).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def publish(path, value, immutable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.q12-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            try:
                os.link(tmp, path)  # Publish complete file, never overwrite another process's evidence.
            except FileExistsError:
                return read(path)
        else:
            os.replace(tmp, path)
        return value
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
