from glob import glob
from setuptools import find_packages, setup


package_name = "vive_ros2"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/rviz", glob("rviz/*.rviz")),
    ],
    install_requires=["pysurvive", "setuptools"],
    tests_require=["pytest"],
    zip_safe=True,
    maintainer="UMI maintainers",
    maintainer_email="maintainer@example.com",
    description="Publish Vive poses from pysurvive to ROS 2.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "vive_pose_node = vive_ros2.vive_pose_node:main",
        ],
    },
)
