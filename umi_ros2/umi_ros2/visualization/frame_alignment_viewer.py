"""Display file-backed image/pose pairs one keypress at a time."""

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import numpy as np

from umi_ros2.postprocess.episode_transform import rotate_vector
from umi_ros2.visualization.frame_alignment import AlignedRecording
from umi_ros2.visualization.replay_source import resolve_replay_items


CAMERA_COLORS = {'wrist': '#f28e2b', 'left': '#8b5cf6'}
AXIS_COLORS = ['#df4141', '#249854', '#287bd1']


class FrameAlignmentViewer:
    """Keep selected images, pose markers and cursor in one redraw."""

    def __init__(self, root, items):
        """Build a manual viewer and open the first ordinary episode."""
        self.root = root
        self.items = items
        self.data = None
        self.index = 0
        self._updating_slider = False
        self.primary = tk.StringVar(value='wrist')
        self.calibrated = tk.BooleanVar(value=True)
        self.status = tk.StringVar()
        self.recording = tk.StringVar()
        root.title('UMI — 逐帧 image / pose 对齐检查')
        root.geometry('1680x1000')
        root.minsize(1000, 700)
        root.protocol('WM_DELETE_WINDOW', self.close)
        top = ttk.Frame(root, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='记录：').pack(side='left')
        self.recording_labels = [
            f'{item.path.parent.name}/{item.path.name}' for item in items]
        recording_box = ttk.Combobox(
            top, textvariable=self.recording,
            values=self.recording_labels, state='readonly', width=34)
        recording_box.pack(side='left', padx=(0, 16))
        recording_box.bind('<<ComboboxSelected>>', self._recording_changed)
        ttk.Label(top, text='逐帧参考相机：').pack(side='left')
        self.camera_box = ttk.Combobox(
            top, textvariable=self.primary, state='readonly', width=8)
        self.camera_box.pack(side='left', padx=(0, 16))
        self.camera_box.bind('<<ComboboxSelected>>', self._camera_changed)
        ttk.Checkbutton(
            top, text='应用标定时差（取消可对比原始时间）',
            variable=self.calibrated, command=self.render).pack(side='left')

        self.figure = Figure(figsize=(16, 8.3), dpi=100)
        self.figure.subplots_adjust(
            left=0.06, right=0.98, bottom=0.10, top=0.93,
            hspace=0.25, wspace=0.24)
        grid = self.figure.add_gridspec(2, 3, height_ratios=[1.6, 1])
        self.image_axes = [self.figure.add_subplot(grid[0, i])
                           for i in range(2)]
        self.path_axes = self.figure.add_subplot(grid[:, 2], projection='3d')
        self.trace_axes = self.figure.add_subplot(grid[1, :2])
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        bottom = ttk.Frame(root, padding=10)
        bottom.pack(fill='x')
        self.previous_button = ttk.Button(
            bottom, text='◀ 上一帧', command=lambda: self.step(-1))
        self.previous_button.pack(side='left')
        self.next_button = ttk.Button(
            bottom, text='下一帧 ▶', command=lambda: self.step(1))
        self.next_button.pack(side='left', padx=8)
        self.slider = tk.Scale(
            bottom, from_=0, to=1, orient='horizontal', showvalue=False,
            command=self._seek)
        self.slider.pack(side='left', fill='x', expand=True, padx=10)
        ttk.Label(bottom, text='Space / → 下一帧，← 上一帧；拖动滑条跳帧').pack(
            side='right')
        ttk.Label(root, textvariable=self.status, padding=(12, 0, 12, 10),
                  justify='left').pack(fill='x')
        root.bind('<Right>', lambda event: self._key_step(event, 1))
        root.bind('<space>', lambda event: self._key_step(event, 1))
        root.bind('<Left>', lambda event: self._key_step(event, -1))
        # Handle these before widget-class bindings (Scale arrows and Button
        # Space would otherwise also act, advancing twice on one keypress).
        for widget in (self.slider, self.previous_button, self.next_button):
            for key, delta in (('<Right>', 1), ('<space>', 1), ('<Left>', -1)):
                widget.bind(key, lambda event, step=delta:
                            self._key_step(event, step))
        root.bind('<Home>', lambda event: self.seek(0))
        root.bind('<End>', lambda event: self.seek(self.frame_count - 1))
        first = next((i for i, item in enumerate(items)
                      if item.path.parent.name == 'episodes'), 0)
        self.load(first)

    @property
    def frame_count(self):
        """Return the selected primary camera's actual frame count."""
        return len(self.data.cameras[self.primary.get()].pts)

    def _key_step(self, event, delta):
        if isinstance(event.widget, ttk.Combobox):
            return
        self.step(delta)
        return 'break'

    def _recording_changed(self, _event):
        try:
            self.load(self.recording_labels.index(self.recording.get()))
        except Exception as error:
            messagebox.showerror('无法加载记录', str(error), parent=self.root)

    def load(self, item_index):
        """Read another recording, closing the previous file handles."""
        candidate = AlignedRecording(self.items[item_index])
        if self.data is not None:
            self.data.close()
        self.data = candidate
        self.recording.set(self.recording_labels[item_index])
        ids = sorted(candidate.cameras, key=lambda key: key != 'wrist')
        self.camera_box['values'] = ids
        if self.primary.get() not in ids:
            self.primary.set(ids[0])
        self.image_ids = ids
        self.index = 0
        self.slider.configure(to=self.frame_count - 1)
        self._setup_plots()
        self.render()

    def _setup_plots(self):
        self.path_axes.clear()
        self.trace_axes.clear()
        points = self.data.positions * 1000
        self.path_axes.plot(*points.T, color='#cad2dc', linewidth=1)
        self.path_line, = self.path_axes.plot(
            [], [], [], color='#3476bb', linewidth=2)
        self.pose_markers = {}
        for camera_id in self.image_ids:
            color = CAMERA_COLORS.get(camera_id, '#555555')
            marker, = self.path_axes.plot(
                [], [], [], 'o', color=color, markersize=8, label=camera_id)
            self.pose_markers[camera_id] = marker
        self.orientation_lines = [
            self.path_axes.plot([], [], [], color=color, linewidth=3)[0]
            for color in AXIS_COLORS]
        center = (points.min(axis=0) + points.max(axis=0)) / 2
        half = max(float(np.ptp(points, axis=0).max()) / 2 * 1.2, 60)
        self.axis_length = half * 0.18
        for setter, value in zip(
                (self.path_axes.set_xlim, self.path_axes.set_ylim,
                 self.path_axes.set_zlim), center):
            setter(value - half, value + half)
        self.path_axes.set_box_aspect((1, 1, 1))
        self.path_axes.set(xlabel='X (mm)', ylabel='Y (mm)', zlabel='Z (mm)',
                           title='TCP pose / recording-start frame')
        self.path_axes.legend(loc='upper right')
        relative_times = self.data.pose_times - self.data.reference_time
        for axis, color, values in zip('XYZ', AXIS_COLORS, points.T):
            self.trace_axes.plot(
                relative_times, values, color=color, linewidth=1, label=axis)
        self.cursor = self.trace_axes.axvline(
            0, color='#444444', linestyle='--')
        self.trace_axes.set(
            xlabel='Seconds from recording-start pose', ylabel='TCP (mm)')
        self.trace_axes.grid(alpha=0.2)
        self.trace_axes.legend(loc='upper right', ncol=3)

    def _camera_changed(self, _event):
        self.slider.configure(to=self.frame_count - 1)
        self.seek(min(self.index, self.frame_count - 1))

    def _seek(self, value):
        if not self._updating_slider:
            self.seek(int(float(value)))

    def step(self, delta):
        """Advance by exactly one primary-camera frame without a timer."""
        self.seek(self.index + delta)

    def seek(self, index):
        """Select a clamped frame and update every display together."""
        self.index = max(0, min(int(index), self.frame_count - 1))
        self.render()

    def render(self):
        """Decode images, then draw their own corrected pose markers."""
        calibrated = self.calibrated.get()
        primary = self.primary.get()
        target, selected = self.data.selection(primary, self.index, calibrated)
        details = []
        for slot, axes in enumerate(self.image_axes):
            axes.clear()
            axes.set_axis_off()
            if slot >= len(self.image_ids):
                axes.text(0.5, 0.5, 'Camera not recorded', ha='center')
                continue
            camera_id = self.image_ids[slot]
            camera = self.data.cameras[camera_id]
            index = selected[camera_id]
            marker = self.pose_markers[camera_id]
            marker.set_data_3d([], [], [])
            if index is None:
                axes.text(0.5, 0.5, 'Outside camera time range', ha='center')
                axes.set_title(camera_id)
                details.append(f'{camera_id}：此时刻无图像')
                continue
            axes.imshow(camera.reader.read(index))
            query = camera.query_times[calibrated][index]
            delta = (query - target) * 1000
            valid = camera.poses[calibrated].valid[index]
            color = CAMERA_COLORS.get(camera_id, '#555555')
            axes.set_title(
                f'{camera_id}  {index + 1}/{len(camera.pts)}  '
                f'PTS {camera.pts[index]:.3f}s\n'
                f'pose t={query - self.data.reference_time:.3f}s  '
                f'delta={delta:+.1f}ms', color=color if valid else 'red')
            if valid:
                position = camera.poses[calibrated].positions[index] * 1000
                marker.set_data_3d(*position[:, None])
                xyz = ', '.join(f'{value:+.1f}' for value in position)
                details.append(f'{camera_id}：XYZ [{xyz}] mm')
            else:
                details.append(f'{camera_id}：pose 无覆盖或间隔 > 100 ms')
                axes.text(0.5, 0.04, 'POSE INVALID', color='red',
                          transform=axes.transAxes, ha='center', fontsize=14,
                          bbox={'facecolor': 'white', 'alpha': 0.8})
        prefix = self.data.pose_times <= target
        self.path_line.set_data_3d(*(self.data.positions[prefix] * 1000).T)
        self.cursor.set_xdata([target - self.data.reference_time] * 2)
        camera = self.data.cameras[primary]
        poses = camera.poses[calibrated]
        for line in self.orientation_lines:
            line.set_data_3d([], [], [])
        if poses.valid[self.index]:
            origin = poses.positions[self.index] * 1000
            orientation = poses.orientations[self.index]
            for line, axis in zip(self.orientation_lines, np.eye(3)):
                tip = origin + rotate_vector(orientation, axis) * (
                    self.axis_length)
                line.set_data_3d(*np.stack([origin, tip]).T)
        mode = '已按标定对齐' if calibrated else '原始时间（未校正）'
        offsets = '；'.join(
            f'{key} {value.video.offset_seconds * 1000:+.2f} ms'
            for key, value in self.data.cameras.items())
        self.status.set(
            f'{mode} | {primary} 第 {self.index + 1}/{self.frame_count} 帧 | '
            f'标定时差：{offsets}\n' + '；'.join(details)
            + '\nXYZ 与坐标轴相对于录制起点；另一相机选校正后最近帧，'
            'delta 为两图时间差，圆点各对应自身图像时刻。')
        self._updating_slider = True
        self.slider.set(self.index)
        self._updating_slider = False
        self.canvas.draw()

    def close(self):
        """Close file handles and the viewer, leaving recordings intact."""
        if self.data is not None:
            self.data.close()
        self.root.destroy()


def main(argv=None):
    """Open a session/recording, defaulting to the newest local session."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'input', nargs='?', help='Session or recording directory')
    args = parser.parse_args(argv)
    root = None
    try:
        candidates = sorted(Path('recordings').glob('online_session_*'))
        source = args.input or (str(candidates[-1]) if candidates else None)
        if source is None:
            raise ValueError('no local session; pass its directory')
        items = resolve_replay_items(source, use_calibration=True)
        root = tk.Tk()
        ttk.Style(root).configure('.', font=('Noto Sans CJK SC', 11))
        FrameAlignmentViewer(root, items)
        print(f'Opened {Path(source).resolve()}\n'
              'Space/Right: next frame; Left: previous frame; '
              'select recording/camera in the window.', flush=True)
        root.mainloop()
        return 0
    except Exception as error:
        if root is not None:
            root.destroy()
        print(f'viewer failed: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
