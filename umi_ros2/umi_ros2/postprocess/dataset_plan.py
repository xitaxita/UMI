"""Describe which transformed episodes form one dataset, and their tasks.

This module needs only NumPy so that both the ROS environment and the
separate LeRobot environment can read the same plan.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from umi_ros2.common.ordering import natural_key

from .transform_session import CONTRACT_VERSION


PLAN_VERSION = 1


@dataclass(frozen=True)
class EpisodeSource:
    """One transformed episode and the session facts exported with it."""

    item: str
    task: str
    source_session: str
    source_episode: str
    video_to_pose_offset_seconds: float = None


def resolve_transformed_items(input_path):
    """Resolve one transformed item or a transformed session root."""
    path = Path(input_path).expanduser().resolve()
    if (path / 'episode_frames.npz').is_file():
        return [path]
    if not (path / 'transform_summary.json').is_file():
        raise ValueError('input has no transform_summary.json')
    episodes = path / 'episodes'
    items = sorted([
        child for child in episodes.iterdir()
        if child.is_dir() and (child / 'episode_frames.npz').is_file()
    ], key=natural_key) if episodes.is_dir() else []
    if not items:
        raise ValueError(f'transformed input contains no episodes: {path}')
    return items


def read_transformed_item(item):
    """Read one transformed report and arrays, checking the contract."""
    item = Path(item)
    report = json.loads(
        (item / 'transform.json').read_text(encoding='utf-8'))
    with np.load(item / 'episode_frames.npz') as values:
        arrays = {name: values[name].copy() for name in values.files}
    version = int(np.asarray(arrays['contract_version']).item())
    if version != CONTRACT_VERSION:
        raise ValueError(
            f'unsupported episode contract version {version}: {item}')
    return report, arrays


def _session_name(source_episode):
    if not source_episode:
        return ''
    session = Path(source_episode).parent.parent
    return session.name if (session / 'session.yaml').is_file() else ''


def sources_for_root(input_path, task, source_session=None):
    """Describe every episode of one transformed root with one task."""
    sources = []
    for item in resolve_transformed_items(input_path):
        report, _ = read_transformed_item(item)
        source_episode = report.get('source_episode') or ''
        offset = report.get('video_to_pose_offset_seconds')
        sources.append(EpisodeSource(
            item=str(item),
            task=task,
            source_session=(
                source_session if source_session is not None
                else _session_name(source_episode)),
            source_episode=source_episode,
            video_to_pose_offset_seconds=(
                None if offset is None else float(offset)),
        ))
    return sources


def task_table(sources):
    """Return unique tasks in first-appearance order (their task_index)."""
    tasks = []
    for source in sources:
        if source.task not in tasks:
            tasks.append(source.task)
    return tasks


def session_summary(sources):
    """Return one record per source session, in dataset order."""
    sessions = {}
    for source in sources:
        entry = sessions.setdefault(source.source_session, {
            'session': source.source_session,
            'task': source.task,
            'video_to_pose_offset_seconds': (
                source.video_to_pose_offset_seconds),
            'episode_count': 0,
        })
        entry['episode_count'] += 1
    return list(sessions.values())


def write_plan(path, sources):
    """Write a plan for a separate exporter process.

    Items below the plan's directory are stored relative to it, so the plan
    stays valid when a finished build directory is moved into place.
    """
    path = Path(path).resolve()
    episodes = []
    for source in sources:
        entry = asdict(source)
        item = Path(source.item).resolve()
        if path.parent in item.parents:
            entry['item'] = str(item.relative_to(path.parent))
        episodes.append(entry)
    path.write_text(json.dumps({
        'plan_version': PLAN_VERSION,
        'episodes': episodes,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read_plan(path):
    """Read a plan written by :func:`write_plan`."""
    path = Path(path).expanduser().resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('plan_version') != PLAN_VERSION:
        raise ValueError(f'unsupported dataset plan: {path}')
    sources = []
    for episode in data['episodes']:
        episode['item'] = str(path.parent / episode['item'])
        sources.append(EpisodeSource(**episode))
    if not sources:
        raise ValueError(f'dataset plan contains no episodes: {path}')
    return sources
