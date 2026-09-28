from glob import glob
from setuptools import find_packages, setup


package_name = 'umi_ros2'

setup(
    name=package_name,
    version='0.2.0',
    packages=find_packages(exclude=('test',)),
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name],
        ),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/rviz', glob('rviz/*.rviz')),
    ],
    install_requires=['setuptools', 'PyYAML'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='UMI maintainers',
    maintainer_email='maintainer@example.com',
    description='Online acquisition and post-processing runtime for UMI.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'vive_pose_node = umi_ros2.vive.pose_node:main',
            'h264_capture_node = '
            'umi_ros2.camera.h264_capture_node:main',
            'episode_keyboard = umi_ros2.camera.episode_keyboard:main',
            'calibrate_time = '
            'umi_ros2.synchronization.calibrate_time:main',
            'generate_aruco_marker = '
            'umi_ros2.synchronization.generate_marker:main',
            'replay_path_node = '
            'umi_ros2.visualization.replay_path_node:main',
            'session_replay_node = '
            'umi_ros2.visualization.session_replay_node:main',
            'align_session = umi_ros2.postprocess.align_session:main',
            'transform_session = '
            'umi_ros2.postprocess.transform_session:main',
            'export_hdf5 = umi_ros2.postprocess.export_hdf5:main',
            'export_lerobot = umi_ros2.postprocess.export_lerobot:main',
            'build_dataset = umi_ros2.postprocess.build_dataset:main',
            'set_session_task = '
            'umi_ros2.session.set_session_task:main',
        ],
    },
)
