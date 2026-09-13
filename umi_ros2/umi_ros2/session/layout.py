"""Create and update the shared online/offline recording layout."""

import tempfile
from datetime import datetime
from pathlib import Path

import yaml


def now_text():
    """Return a local, timezone-aware ISO timestamp."""
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def timestamp_id():
    """Return a filesystem-safe timestamp with microsecond uniqueness."""
    return datetime.now().strftime('%Y%m%d_%H%M%S_%f')


def create_online_session(recordings_root):
    """Create one online session containing calibration and episode groups."""
    root = Path(recordings_root).expanduser().resolve()
    session = root / f'online_session_{timestamp_id()}'
    session.mkdir(parents=True, exist_ok=False)
    (session / 'calibration').mkdir()
    (session / 'episodes').mkdir()
    _write(session, {
        'schema_version': 1,
        'session_id': session.name,
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


def create_offline_session(session_output):
    """Create the provisional pose-only offline session layout."""
    session = Path(session_output).expanduser().resolve()
    session.mkdir(parents=True, exist_ok=False)
    (session / 'calibration').mkdir()
    _write(session, {
        'schema_version': 1,
        'session_id': session.name,
        'mode': 'offline',
        'status': 'active',
        'started_at': now_text(),
        'ended_at': None,
        'layout': {
            'calibration': 'calibration',
            'pose': 'pose',
        },
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
    }
    metadata.setdefault('recordings', []).append(item)
    _write(session, metadata)


def read_session(session):
    """Read and validate one session metadata mapping."""
    path = Path(session) / 'session.yaml'
    data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'invalid session metadata: {path}')
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
