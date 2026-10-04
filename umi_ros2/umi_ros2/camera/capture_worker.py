"""Persistent camera worker with one-time warmup and episode recording."""

import json
import queue
import signal
import sys
import threading
import time
from pathlib import Path

from umi_ros2.camera.capture_pipeline import WarmupGate
from umi_ros2.camera.stream_protocol import NO_SOURCE_PTS, PREVIEW_HEADER


def _quote(value):
    return json.dumps(str(value))


class CaptureWorker:
    """Keep UVC preview alive and attach one encoder per episode."""

    def __init__(self, config):
        """Create the persistent camera and its episode-control state."""
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        self.Gst = Gst
        self.config = config
        self.gate = WarmupGate(config['warmup_seconds'], config['fps'])
        self.commands = queue.Queue()
        self.lock = threading.Lock()
        self.recorder = None
        self.appsrc = None
        self.timing = None
        self.stop_requested = False
        self.last_receive_ns = time.monotonic_ns()
        self.source_frames = 0
        self.no_frame_warned = False
        self.status_path = Path(config['status_path'])
        self.status = {'state': 'warming_up', 'error': ''}
        self._save_status()
        self.camera = Gst.parse_launch(self._camera_description())
        self.camera.get_by_name('capture_sink').connect(
            'new-sample', self._on_sample)
        self.camera.get_by_name('preview_sink').connect(
            'new-sample', self._on_preview)
        self.camera_bus = self.camera.get_bus()

    def _camera_description(self):
        c = self.config
        input_format = c.get('input_format', 'MJPEG')
        if input_format == 'MJPEG':
            input_caps = (
                f'image/jpeg,width={c["width"]},height={c["height"]},'
                f'framerate={c["fps"]}/1')
            decode = ['jpegdec', '!']
        elif input_format == 'YUYV':
            input_caps = (
                f'video/x-raw,format=YUY2,width={c["width"]},'
                f'height={c["height"]},framerate={c["fps"]}/1')
            decode = []
        else:
            raise ValueError(
                f'Unsupported camera input_format: {input_format}')
        source = [
            'videotestsrc', 'name=camera', 'is-live=true', '!'
        ] if c.get('test_source') else [
            'v4l2src', 'name=camera', f'device={_quote(c["device"])}',
            f'io-mode={c["io_mode"]}', 'do-timestamp=true', '!',
        ]
        test_encoder = [
            'video/x-raw,width=320,height=240,framerate=30/1',
            '!', 'jpegenc', '!'
        ] if c.get('test_source') and input_format == 'MJPEG' else []
        return ' '.join(source + test_encoder + [
            input_caps, '!', 'tee', 'name=stream',
            'stream.', '!', 'queue', 'max-size-buffers=2',
            'max-size-bytes=0', 'max-size-time=0', 'leaky=downstream', '!',
        ] + decode + [
            'videoconvert', '!', 'videoscale', '!',
            f'video/x-raw,format=BGR,width={c["preview_width"]},'
            f'height={c["preview_height"]}', '!', 'appsink',
            'name=preview_sink', 'emit-signals=true', 'sync=false',
            'max-buffers=2', 'drop=true',
            'stream.', '!', 'queue', 'leaky=no', 'max-size-buffers=4',
            'max-size-bytes=0', 'max-size-time=0', '!', 'appsink',
            'name=capture_sink', 'emit-signals=true', 'sync=false',
            'max-buffers=2', 'drop=false',
        ])

    def _encoder_description(self, output):
        c = self.config
        input_format = c.get('input_format', 'MJPEG')
        if input_format == 'MJPEG':
            input_caps = (
                f'image/jpeg,width={c["width"]},height={c["height"]},'
                f'framerate={c["fps"]}/1')
            decode = ['jpegdec', '!']
        elif input_format == 'YUYV':
            input_caps = (
                f'video/x-raw,format=YUY2,width={c["width"]},'
                f'height={c["height"]},framerate={c["fps"]}/1')
            decode = []
        else:
            raise ValueError(
                f'Unsupported camera input_format: {input_format}')
        return ' '.join([
            'appsrc', 'name=episode_source', 'is-live=true', 'format=time',
            'block=true',
            f'caps={input_caps}', '!', 'queue', 'leaky=no',
            'max-size-buffers=120', 'max-size-bytes=0', 'max-size-time=0',
            '!',
        ] + decode + [
            'videoconvert', '!',
            'video/x-raw,format=I420', '!', 'x264enc',
            'speed-preset=ultrafast', 'tune=zerolatency',
            f'bitrate={c["bitrate_kbps"]}', f'key-int-max={c["fps"]}',
            '!', 'h264parse', '!', 'mp4mux', 'faststart=true', '!',
            'filesink', f'location={_quote(output)}', 'async=false',
        ])

    def _save_status(self):
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(
            json.dumps(self.status, indent=2) + '\n', encoding='utf-8')

    def _on_preview(self, sink):
        """Write one BGR frame with source PTS and host receive time."""
        Gst = self.Gst
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        mapped, info = buffer.map(Gst.MapFlags.READ)
        if not mapped:
            return Gst.FlowReturn.ERROR
        try:
            data = bytes(info.data)
        finally:
            buffer.unmap(info)
        expected = (
            self.config['preview_width'] * self.config['preview_height'] * 3)
        if len(data) != expected:
            return Gst.FlowReturn.ERROR
        pts = (NO_SOURCE_PTS if buffer.pts == Gst.CLOCK_TIME_NONE
               else int(buffer.pts))
        sys.stdout.buffer.write(
            PREVIEW_HEADER.pack(pts, time.time_ns()) + data)
        sys.stdout.buffer.flush()
        return Gst.FlowReturn.OK

    def _on_sample(self, sink):
        Gst = self.Gst
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        now = time.monotonic_ns()
        self.last_receive_ns = now
        self.source_frames += 1
        if self.source_frames == 1 and self.no_frame_warned:
            self.status.pop('warning', None)
            self._save_status()
        pts = buffer.pts if buffer.pts != Gst.CLOCK_TIME_NONE else None
        valid = pts is not None and not buffer.has_flags(
            Gst.BufferFlags.CORRUPTED | Gst.BufferFlags.DISCONT)
        if not self.gate.started:
            self.gate.accept(pts, now, valid)
            if self.gate.started:
                self.status.update({
                    'state': 'waiting', 'ready_monotonic_ns': now,
                    'ready_unix_ns': time.time_ns(),
                    'excluded_warmup_frames': self.gate.excluded,
                })
                self._save_status()
                print('Camera warmup complete; waiting for episode',
                      file=sys.stderr, flush=True)
        with self.lock:
            if self.appsrc is None:
                return Gst.FlowReturn.OK
            copied = buffer.copy_deep()
            if self.timing['accepted_frames'] == 0:
                self.timing['first_source_pts_ns'] = pts
                self.timing['first_receive_monotonic_ns'] = now
                self.timing['first_receive_unix_ns'] = time.time_ns()
            base = self.timing['first_source_pts_ns']
            copied.pts = pts - base if pts is not None else Gst.CLOCK_TIME_NONE
            copied.dts = Gst.CLOCK_TIME_NONE
            self.timing['accepted_frames'] += 1
            self.timing['last_source_pts_ns'] = pts
            result = self.appsrc.emit('push-buffer', copied)
            if result != Gst.FlowReturn.OK:
                self.timing['push_error'] = str(result)
            return result

    def start_episode(self, command):
        """Open a fresh encoder while camera and preview keep running."""
        if not self.gate.started or self.recorder is not None:
            return
        recorder = self.Gst.parse_launch(
            self._encoder_description(command['output_path']))
        if recorder.set_state(
                self.Gst.State.PLAYING) == self.Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('Episode encoder could not start')
        with self.lock:
            self.recorder = recorder
            self.appsrc = recorder.get_by_name('episode_source')
            self.timing = {
                'status': 'recording',
                'timing_path': command['timing_path'],
                'camera_id': self.config.get('camera_id'),
                'image_field': self.config.get('image_field'),
                'accepted_frames': 0,
                'input': self.config.get('input_format', 'MJPEG'),
                'output': 'H264',
                'camera_warmup_performed_once': True,
                'timestamp_note': 'Host receipt and source PTS, not exposure '
                'time; pose and video require later synchronization.',
            }
            self.status['state'] = 'recording'
            self._write_timing(self.timing)
            self._save_status()
        print(f'Episode recording started: {command["output_path"]}',
              file=sys.stderr, flush=True)

    @staticmethod
    def _write_timing(timing):
        Path(timing['timing_path']).write_text(
            json.dumps(timing, indent=2) + '\n', encoding='utf-8')

    def stop_episode(self):
        """Stop accepting frames, send EOS, and return to waiting state."""
        with self.lock:
            recorder = self.recorder
            appsrc = self.appsrc
            timing = self.timing
            self.appsrc = None
        if recorder is None:
            return
        appsrc.emit('end-of-stream')
        message = recorder.get_bus().timed_pop_filtered(
            15 * self.Gst.SECOND,
            self.Gst.MessageType.ERROR | self.Gst.MessageType.EOS)
        complete = (
            message is not None
            and message.type == self.Gst.MessageType.EOS
        )
        if (message is not None
                and message.type == self.Gst.MessageType.ERROR):
            error, debug = message.parse_error()
            timing['error'] = f'{error}: {debug}'
        recorder.set_state(self.Gst.State.NULL)
        with self.lock:
            self.recorder = None
            self.timing = None
        timing['status'] = 'complete' if complete else 'failed'
        self._write_timing(timing)
        self.status['state'] = 'waiting'
        self._save_status()
        print('Episode recording finalized', file=sys.stderr, flush=True)

    def _read_commands(self):
        for line in sys.stdin:
            try:
                self.commands.put(json.loads(line))
            except json.JSONDecodeError as error:
                print(f'Invalid control command: {error}',
                      file=sys.stderr, flush=True)

    def run(self):
        """Run the persistent camera until process shutdown."""
        Gst = self.Gst
        no_frame_hint = (
            'check USB connection and selected color video device'
            if self.config.get('input_format') == 'YUYV'
            else 'check camera Webcam mode, USB connection and selected '
                 'video device')
        threading.Thread(target=self._read_commands, daemon=True).start()
        if (self.camera.set_state(Gst.State.PLAYING)
                == Gst.StateChangeReturn.FAILURE):
            raise RuntimeError('Camera pipeline could not start')
        timeout = self.config['startup_timeout_seconds']
        started = time.monotonic()
        try:
            while not self.stop_requested:
                try:
                    command = self.commands.get_nowait()
                    if command['command'] == 'start':
                        self.start_episode(command)
                    elif command['command'] == 'stop':
                        self.stop_episode()
                except queue.Empty:
                    pass
                message = self.camera_bus.timed_pop_filtered(
                    100 * Gst.MSECOND, Gst.MessageType.ERROR)
                if message is not None:
                    error, debug = message.parse_error()
                    raise RuntimeError(f'{error}: {debug}')
                now = time.monotonic()
                if (self.source_frames == 0 and not self.no_frame_warned
                        and now - started > 5):
                    device = self.config.get('device', 'camera')
                    self.status['warning'] = (
                        f'No frames from {device}; {no_frame_hint}')
                    self._save_status()
                    print(self.status['warning'], file=sys.stderr,
                          flush=True)
                    self.no_frame_warned = True
                if not self.gate.started and now - started > timeout:
                    if self.source_frames == 0:
                        device = self.config.get('device', 'camera')
                        raise RuntimeError(
                            f'No frames from {device}'
                            f' within {timeout:g} seconds; {no_frame_hint}')
                    raise RuntimeError('Camera did not stabilize in time')
                stalled = (
                    time.monotonic_ns() - self.last_receive_ns
                ) / 1e9
                if self.source_frames > 0 and stalled > timeout:
                    raise RuntimeError('Camera stopped providing frames')
        finally:
            self.stop_episode()
            self.camera.set_state(Gst.State.NULL)
        return 0


def main():
    """Read JSON configuration and run the isolated persistent worker."""
    worker = CaptureWorker(json.loads(sys.argv[1]))

    def stop(signum, frame):
        worker.stop_requested = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        return worker.run()
    except Exception as error:
        worker.status.update({'state': 'failed', 'error': str(error)})
        worker._save_status()
        print(f'Camera capture failed: {error}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
