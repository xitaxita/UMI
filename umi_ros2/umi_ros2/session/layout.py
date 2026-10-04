"""Create and update the online session recording layout."""

import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import yaml


SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
CALIBRATION_PATTERN = re.compile(r'^calibration_(\d+)$')
# Raw calibration inputs copied to a new session; derived results never are.
CALIBRATION_RAW_FILES = (
    'video.mp4', 'video.timing.json', 'video.validation.json')
CALIBRATION_RAW_DIRECTORIES = ('pose', 'cameras')


def camera_video_path(recording, camera_id):
    """Return the canonical MP4 path for one recorded camera."""
    return Path(recording) / 'cameras' / camera_id / 'video.mp4'


def resolve_video_path(recording, camera_id='wrist'):
    """Read the camera directory, accepting legacy root wrist files."""
    current = camera_video_path(recording, camera_id)
    if current.parent.exists():
        return current
    legacy = Path(recording) / 'video.mp4'
    if (camera_id == 'wrist'
            and (legacy.exists()
                 or legacy.with_suffix('.timing.json').exists())):
        return legacy
    return current


def resolve_calibration_camera(recording, camera_id=None):
    """Infer one calibration stream; legacy recordings default to wrist."""
    if camera_id is not None:
        if not re.fullmatch(r'[A-Za-z0-9_]+', camera_id):
            raise ValueError('camera_id must be a path-safe ID')
        return camera_id
    videos = list((Path(recording) / 'cameras').glob('*/video.mp4'))
    return videos[0].parent.name if len(videos) == 1 else 'wrist'


def update_temporal_calibration(session, camera_id, result):
    """Replace one camera result and retain the wrist compatibility view."""
    metadata = read_session(session)
    metadata.setdefault('temporal_calibrations', {})[camera_id] = result
    if camera_id == 'wrist':
        metadata['temporal_calibration'] = result.copy()
    _write(Path(session), metadata)


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


def create_online_session(recordings_root, task='', image_streams=None):
    """Create one single-task online session with calibration and episodes."""
    root = Path(recordings_root).expanduser().resolve()
    session = root / f'online_session_{timestamp_id()}'
    session.mkdir(parents=True, exist_ok=False)
    (session / 'calibration').mkdir()
    (session / 'episodes').mkdir()
    metadata = {
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
        'temporal_calibrations': {},
        'recordings': [],
    }
    if image_streams is not None:
        metadata['image_streams'] = list(image_streams)
    _write(session, metadata)
    return session


def update_session(session, **changes):
    """Merge top-level fields into session.yaml using an atomic replace."""
    session = Path(session)
    metadata = read_session(session)
    metadata.update(changes)
    _write(session, metadata)


def register_recording(
        session, recording, kind, status='complete', copied_from=None,
        image_streams=None):
    """Index one recording, replacing an earlier attempt at the same path."""
    session = Path(session)
    metadata = read_session(session)
    item = {
        'kind': kind,
        'path': str(Path(recording).relative_to(session)),
        'status': status,
        'ended_at': now_text(),
        'task': session_task(metadata),
    }
    if copied_from is not None:
        # Provenance only: post-processing never reads this field.
        item['copied_from'] = str(copied_from)
    if image_streams is not None:
        item['image_streams'] = list(image_streams)
    recordings = metadata.setdefault('recordings', [])
    for index, previous in enumerate(recordings):
        if previous.get('path') == item['path']:
            recordings[index] = item
            break
    else:
        recordings.append(item)
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


def calibration_number(path):
    """Return the sequence number of ``calibration_<n>``, else ``None``."""
    match = CALIBRATION_PATTERN.match(Path(path).name)
    return int(match.group(1)) if match else None


def calibration_directories(session):
    """Return ``calibration_<n>`` directories ordered by sequence number."""
    root = Path(session) / 'calibration'
    if not root.is_dir():
        return []
    found = [
        child for child in root.iterdir()
        if child.is_dir() and calibration_number(child) is not None
    ]
    return sorted(found, key=calibration_number)


def latest_calibration(session, camera_id='wrist'):
    """Return the newest recording for a camera; legacy consumers use wrist."""
    metadata = read_session(session)
    excluded = {item.get('path') for item in metadata.get('recordings', [])
                if item.get('kind') == 'calibration'
                and item.get('status') in ('failed', 'rejected')}
    candidates = [path for path in calibration_directories(session)
                  if str(path.relative_to(session)) not in excluded
                  and resolve_calibration_camera(path) == camera_id]
    if not candidates:
        raise ValueError(f'session contains no calibration episode: {session}')
    return candidates[-1]


def copy_calibration_raw(source_session, target_session):
    """Copy completed raw calibrations into a new session; return copies.

    Only ``CALIBRATION_RAW_FILES`` and ``CALIBRATION_RAW_DIRECTORIES`` are
    copied, keeping the sequence number. Each item is staged in a hidden
    ``.calibration_<n>.partial`` directory and renamed when complete, then
    registered with ``copied_from``. Derived calibration results stay behind.
    """
    source_session = Path(source_session)
    target_session = Path(target_session)
    source_metadata = read_session(source_session)
    complete = {
        item.get('path'): item
        for item in source_metadata.get('recordings', [])
        if item.get('kind') == 'calibration'
        and item.get('status') == 'complete'
    }
    copied = []
    target_root = target_session / 'calibration'
    target_root.mkdir(exist_ok=True)
    for source in calibration_directories(source_session):
        relative = str(source.relative_to(source_session))
        if relative not in complete:
            continue
        video = resolve_video_path(source, resolve_calibration_camera(source))
        required = (video, video.with_suffix('.timing.json'),
                    source / 'pose')
        missing = [str(path.relative_to(source))
                   for path in required if not path.exists()]
        if missing:
            raise ValueError(
                f'calibration {source} is missing {", ".join(missing)}')
        target = target_root / source.name
        partial = target_root / f'.{source.name}.partial'
        if target.exists() or partial.exists():
            raise FileExistsError(f'calibration target exists: {target}')
        try:
            partial.mkdir()
            for name in CALIBRATION_RAW_FILES:
                if (source / name).is_file():
                    shutil.copy2(source / name, partial / name)
            for name in CALIBRATION_RAW_DIRECTORIES:
                if (source / name).is_dir():
                    shutil.copytree(source / name, partial / name)
            partial.rename(target)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
        register_recording(
            target_session, target, 'calibration',
            copied_from=f'{source_session.name}/{relative}',
            image_streams=complete[relative].get('image_streams'))
        copied.append(target)
    return copied


def switch_session(previous_session, recordings_root, task='',
                   image_streams=None):
    """Open the next single-task session and copy raw calibrations into it.

    All-or-nothing: on failure the new session is removed and the previous
    session is left untouched and active. Returns ``(session, copied)``.
    """
    previous_session = Path(previous_session)
    session = create_online_session(
        recordings_root, task, image_streams=image_streams)
    try:
        copied = copy_calibration_raw(previous_session, session)
    except BaseException:
        shutil.rmtree(session, ignore_errors=True)
        raise
    update_session(previous_session, status='complete', ended_at=now_text())
    return session, copied


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
