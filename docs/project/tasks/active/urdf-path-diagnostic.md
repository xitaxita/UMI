# URDF path diagnostic overlay

## Goal

Provide an optional RViz view that overlays the published Vive TCP path with a
user-supplied URDF model while leaving the acquisition and normal RViz entry
points unchanged.

## Additive implementation

- `umi_ros2/launch/urdf_path_diagnostic.launch.py` reads a plain URDF file,
  infers its root link when possible, starts `robot_state_publisher` and
  `joint_state_publisher`, publishes a configurable static transform from the
  Vive world frame to that root link, and opens a diagnostic RViz instance.
- `umi_ros2/rviz/urdf_path_diagnostic.rviz` displays the URDF, TF and
  `/vive/path` in a shared `vive_world` frame.
- This launch is run alongside an existing Vive acquisition/view launch. It
  does not start Vive, record data, or alter the established launch files.
- Root placement is an operator-supplied transform. The model is not
  automatically registered to the path. Movable joints use the
  `joint_state_publisher` default positions until a future live or recorded
  joint-state source is connected.

## Current limitation

The user's URDF has not yet been added. The launch and RViz configuration are
therefore prepared but have not been checked against the real robot model or
visually accepted. Runtime package dependencies on
`robot_state_publisher` and `joint_state_publisher` must be declared and
installed before distributing this entry point.

## Next acceptance steps

1. Add the validated URDF and identify the intended root/base link.
2. Install and declare the two state-publisher runtime dependencies.
3. Rebuild and parse the installed launch file.
4. Run alongside the existing Vive source and adjust `base_x/y/z` and
   `base_roll/pitch/yaw` so robot geometry and TCP path share the intended
   physical reference.
5. Confirm RobotModel, `/vive/path`, and TF appear together in RViz.
