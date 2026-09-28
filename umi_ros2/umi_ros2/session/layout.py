"""Create and update the online session recording layout."""

import tempfile
from datetime import datetime
from pathlib import Path

import yaml


SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)


def now_text():
    """Return a local, timezone-aware ISO timestamp."""
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def timestamp_id():
    """Return a filesystem-safe timestamp with microsecond uniqueness."""
    return datetime.now().strftime('%Y%m%d_%H%M%S_%f')


def normalize_task(task):
    """Return a task as stripped text; ``None`` means no task."""
    return '' if task is None else str(task).strip()


def session_task(metadata):
    """Return the session task; v1 metadata without a task is empty."""
    return normalize_task(metadata.get('task'))


def create_online_session(recordings_root, task=''):
    """Create one single-task online session with calibration and episodes."""
    root = Path(recordings_root).expanduser().resolve()
    session = root / f'online_session_{timestamp_id()}'
    session.mkdir(parents=True, exist_ok=False)
    (session / 'calibration').mkdir()
    (session / 'episodes').mkdir()
    _write(session, {
        'schema_version': SCHEMA_VERSION,
        'session_id': session.name,
        'task': normalize_task(task),
        'mode': 'online',
        'status': 'active',
        'started_at': now_text(),
        'ended_at': None,
        'layout': {
            'calibration': 'calibration',
            'episodes': 'episodes',
        },
        'temporal_calibration': {
            'status': 'not_calibrated',
            'result': None,
        },
        'recordings': [],
    })
    return session


def update_session(session, **changes):
    """Merge top-level fields into session.yaml using an atomic replace."""
    session = Path(session)
    metadata = read_session(session)
    metadata.update(changes)
    _write(session, metadata)


def register_recording(session, recording, kind, status='complete'):
    """Append a completed online recording to the session index."""
    session = Path(session)
    metadata = read_session(session)
    item = {
        'kind': kind,
        'path': str(Path(recording).relative_to(session)),
        'status': status,
        'ended_at': now_text(),
        'task': session_task(metadata),
    }
    metadata.setdefault('recordings', []).append(item)
    _write(session, metadata)


def set_task(session, task):
    """Set the authoritative task, upgrading v1 metadata to v2.

    Recording ``task`` snapshots are provenance and are left unchanged.
    """
    session = Path(session)
    metadata = read_session(session)
    upgraded = {}
    for key, value in metadata.items():
        if key == 'task':
            continue
        upgraded[key] = value
        if key == 'session_id':
            upgraded['task'] = None
    upgraded['task'] = normalize_task(task)
    upgraded['schema_version'] = SCHEMA_VERSION
    upgraded['task_updated_at'] = now_text()
    _write(session, upgraded)
    return upgraded


def read_session(session):
    """Read and validate one v1 or v2 session metadata mapping."""
    path = Path(session) / 'session.yaml'
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'invalid session metadata: {path}')
    version = data.get('schema_version', 1)
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(
            f'unsupported session schema_version {version!r}: {path}')
    return data


def _write(session, metadata):
    path = Path(session) / 'session.yaml'
    with tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=path.parent,
        prefix='.session.', suffix='.yaml', delete=False,
    ) as temporary:
        yaml.safe_dump(
            metadata, temporary, allow_unicode=True, sort_keys=False)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)
