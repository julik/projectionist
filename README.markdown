## What is Projectionist?

Projectionist is a wonderful handy Nuke module with scripts for creating projection setups. Currently three commands are provided:

* Create a projector from this camera
* Create projection alley from this camera
* Convert this camera to nodal with dolly axis

For both to work you need to select a camera. The camera needs to be unlinked from it's FBX file if you use that.

### Create a projector from this camera

This will create a copy of your current camera, freeze it at the frame you are in the script, 
and optionally create you a Project3D and a FrameHold you can plug your footage into. This camera is linked to the original camera
and has a knob which you can use to timewarp the camera (when you animate the `at` knob it will sample the source camera from the provided frame).

This is something you have to do alot so this setup is automated to the top.

### Create projection alley from this camera

This will take your camera across a framerange, and create a number of projecting cameras frozen at frames in the framerange. From each one of these it will
create a frame hold node and a project3d shader, and the shaders will all be combined. So the output of this command is a group that has all the projection cameras
embedded into it, as well as shaders - it's output is also a shader. Connect a premultiplied plate into the input of the group, and it's output is a projection shader
with multiple frames layered on top of each other. Layering uses alpha masking, so if you roto out your talent you will get a ready cleanplate out of this in no time flat.

It's also majorly useful for extracting textures from big camera moves - like flyovers and aerial shots.

### Convert this camera to nodal with dolly axis

This will extract the position animation of your camera into a separate Axis node (your "dolly"). The camera will be then repositioned
to the origin of the scene and parented to the dolly axis - so that you have a moving camera mount that does not rotate, and 
under it the camera itself. Having done that you can easily attach your nodal elements (environment maps, lights and cards) to the
axis that drives the camera and the elements will be properly positioned yet flying together with the camera mount.

## Installation

Copy the directory somewhere, no matter where. Then import the module into your Nuke's init.py or menu.py, like this:

	sys.path.append("/path/to/the/directory/where/projectionist/is/in")
	import projectionist

Note that projectionist does NOT contain any gizmos, so your script will not be polluted - it just helps you _create_ things.

## Contributions and fixes

When contributing to Projectionist please set your editor to LF (UNIX) line breaks and use 4 spaces for indentation.

## Credits

Created by Julik Tarkhanov <me@julik.nl> in Amsterdam, 2011.
