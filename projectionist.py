import nuke, nukescripts, os, sys, re, inspect
__version__ = (2, 1, 0)

MY_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Use self-detecting path for icons.
ICONS_PATH =  os.path.join(MY_MODULE_DIR, "icons")

OPTIMUM_DAG_OFFSET = 100
CAMERA_NODES = ["Camera", "Camera2", "SyCamera"]

def func_shorthand(symbol):
    """
    Returns the fully qualified function call with it's module so that it can be used in Nuke's menus,
    even if your function is nested 6 levels deep in a module
    func_shorthand(do_this) #=> "some.module.another.do_this()"
    """
    my_module = inspect.getmodule(symbol).__name__
    return '.'.join([my_module, symbol.__name__]) + '()'

def ensure_camera_selected(selected_camera):
    """
    Helps ensure that a camera is indeed selected
    """
    if not selected_camera or not (selected_camera.Class() in CAMERA_NODES):
        nuke.message("Please select a camera!")
        return False
    else:
        return True

def set_frame_at():
    """
    Gets assigned to the button callback
    """
    n = nuke.thisNode()
    n["at"].setValue(int(nuke.root()["frame"].getValue()))
    
def create_camera_at(selected_camera, at_frame, link_to_original = False):
    """
    Creates a camera that is a frozen copy of the currently selected camera at the current frame.
    The freeze frame is controlled with a separated knob and can be animated for timewarp effects.
    Frozen camera will be returned. If link_to_original is set to True the camera will be linked to
    the original camera and can therefore be timewarped with the created "at" knob. However it's
    oftentimes better to just create a camera that is not linked to not pollute the DAG with extra connections,
    so that's what we do by default
    """
    if not ensure_camera_selected(selected_camera):
        return
        
    selected_camera_name = selected_camera.name()
    
    # Create a fresh cam, make sure it has the same CameraOp class as the camera
    # we are replicating. This is important when we are using non-standard Camera ops.
    camera_op_class = selected_camera.Class()
    
    # Create the locked camera without changing any DAG connections.
    # This is analogous to creating a Nuke node using a constructor from the
    # nodes namespace
    #    cam = nuke.nodes.Camera2()
    locked_cam = getattr(nuke.nodes, camera_op_class)() # Do not manage connections
    
    locked_cam.setName("%s_Proj" % selected_camera_name)
    
    if link_to_original:
        # Add the "at" knob
        tab = nuke.Tab_Knob('Frame') 
        locked_cam.addKnob(tab)
        
        at = nuke.Int_Knob('at')
        at.setValue(at_frame)
        locked_cam.addKnob(at)
        
        # We need to use the textual function shorthand for the button, we cannot link to the Python function closure
        tframe = nuke.PyScript_Knob("Py_setThisFrame", "Set to this frame", func_shorthand(set_frame_at))
        tframe.clearFlag(nuke.STARTLINE)
        locked_cam.addKnob(tframe)
    
    # Walk the animated knobs on the source camera and bind the projected camera to them.
    # We walk the knobs on the LOCKED cam so that we do not copy over the user knobs!
    for knob_name, knob_on_locked in locked_cam.knobs().iteritems():
        knob = selected_camera[knob_name]
        if knob.isAnimated():
            # When we create a shitload of cameras it's better to just unlink them
            if link_to_original:
                knob_on_locked.setExpression(selected_camera_name + "." + knob_name + "(at)")
            else:
                try:
                    knob_on_locked.setValue(knob.getValueAt(at_frame))
                except TypeError: # they could not ensure that getValue and setValue have same types
                    pass
        elif hasattr(knob, "notDefault") and knob.notDefault():
            try:
                knob_on_locked.setValue(knob.getValue())
            except TypeError: # they could not ensure that getValue and setValue have same types
                pass
    
    # Connect the created cam to the same input (if there is one like another Camera or an Axis)
    cam_input = selected_camera.input(0)
    locked_cam.setInput(0, cam_input)
    
    # Show a helpful reminder on the node label
    # For String and File knobs you have to put the expression in brackets directly into the knob's value. Like so: 
    if link_to_original:
        locked_cam["label"].setValue("at [value at]")
    else:
        locked_cam["label"].setValue("at %d" % at_frame)
    
    # Give non-default color to projection cameras
    locked_cam["tile_color"].setValue(0xc97fff)
    locked_cam["gl_color"].setValue(0xc97fff)
    
    # Offset it in the schematic since due to node copying knob for knob our cam is now on top of the original
    # in the DAG
    locked_cam["xpos"].setValue( locked_cam["xpos"].getValue() + OPTIMUM_DAG_OFFSET)
    return locked_cam

def create_camera_at_and_shader(selected_camera, at_frame, link_to_original = False):
    cam = create_camera_at(selected_camera, at_frame, link_to_original)
    hold = nuke.nodes.FrameHold()
    
    hold["xpos"].setValue( cam["xpos"].getValue() + OPTIMUM_DAG_OFFSET)
    if link_to_original:
        hold["first_frame"].setExpression(cam.name() + ".at")
    else:
        hold["first_frame"].setValue(at_frame)
    
    project3d = nuke.nodes.Project3D()
    project3d["xpos"].setValue( hold["xpos"].getValue())
    project3d["ypos"].setValue( hold["ypos"].getValue() + 32)
    
    set_inputs(project3d, hold, cam)

def set_inputs(node, *inputs):
    """
    Sets inputs of the passed node in the order of the passed input nodes.
    The first node will become input 0 and so on
    """
    for idx, one_input in enumerate(inputs):
        node.setInput(idx, one_input)

def create_projection_alley(sel_cam, frame_numbers, link_cameras, project3d_setup_callback):
    """
    Takes an animated camera, and instances it across the passed list of frames. Each camera projects a hold frame
    from the image input, and all of the projections are combined into one shader that can be applied to any geometry.
    The input should be premultiplied so that shader layering works properly.
    """
    g = nuke.nodes.Group()
    g.begin()
    
    shader_stack = []
    
    # Isolate outside of the bbox so that te shader does not cover things it's not supposed to
    inp = nuke.nodes.Input()
    dot = nuke.nodes.BlackOutside()
    dot.setInput(0, inp)
    
    proj_cam = None
    last_x = sel_cam["xpos"].getValue()
    
    for frame_number in frame_numbers:
        cam = create_camera_at(sel_cam, frame_number, link_cameras)
        
        # Make the camera invisible since too many cameras just clobber the viewport
        # TODO: make optional
        cam["display"].setValue("off")
        
        # Make it look Good(tm)
        last_x = last_x + OPTIMUM_DAG_OFFSET
        cam["xpos"].setValue(last_x)
        
        frame_hold = nuke.nodes.FrameHold()
        frame_hold.setInput(0, dot)

        if link_cameras:
            frame_hold["first_frame"].setExpression(proj_cam.name() + ".at")
        else:
            frame_hold["first_frame"].setValue(frame_number)
        
        project3d = nuke.nodes.Project3D()
        
        # Pass the p3d to the callback
        project3d_setup_callback(project3d)
        
        # First set the zero input (avoid Nuke bug)
        set_inputs(project3d, frame_hold, cam)
        shader_stack.append(project3d)
        
    if len(shader_stack) > 1:
        shader = shader_stack.pop(0) # just implement a fucking stack.shift() nazis
        while len(shader_stack) > 0:
            merge_mat = nuke.nodes.MergeMat()
            merge_mat.setInput(0, shader)
            merge_mat.setInput(1, shader_stack.pop(0)) # B input is first
            shader = merge_mat # :-)
    else:
        shader = shader_stack[0]
    
    # End dot for the shaders
    end_dot = nuke.nodes.Output()
    end_dot.setInput(0, shader)
    
    g.end()
    g["xpos"].setValue( sel_cam["xpos"].getValue() + OPTIMUM_DAG_OFFSET)
    g["ypos"].setValue( sel_cam["ypos"].getValue() )
    
    return g


def create_projection_alley_panel():
    if not ensure_camera_selected(nuke.selectedNode()):
        return
    
    p = nukescripts.panels.PythonPanel("Create projection alley")

    p.addKnob(nuke.Int_Knob("start", "First frame to project"))
    p.knobs()["start"].setValue(int(nuke.root()["first_frame"].getValue()))
    
    p.addKnob(nuke.Int_Knob("finish", "Last frame to project"))
    p.knobs()["finish"].setValue(int(nuke.root()["last_frame"].getValue()))
    
    p.addKnob(nuke.Int_Knob("step", "Step (project every N frames)"))
    p.knobs()["step"].setValue(int(nuke.root().fps()))
    
    k = nuke.Boolean_Knob("backwards", "Layer last frame to first frame")
    k.setFlag(nuke.STARTLINE)
    k.setTooltip("Projected frames are layered first to last (last frame comes on top). When checked the first frames will come out on top")
    p.addKnob(k)
    
    k = nuke.Boolean_Knob("link", "Create linked cameras")
    k.setTooltip("Creates a linked multicam rig that will update if you change the camera path")
    k.setFlag(nuke.STARTLINE)
    p.addKnob(k)
    
    p.addKnob(nuke.Text_Knob('divdr', 'Project3D Parameters', ''))
    
    # Add the "project on" knob. Normally we would only want to project against the normals.
    k = nuke.Enumeration_Knob("project_on", "project on", ['both', 'front', 'back'])
    k.setFlag(nuke.STARTLINE)
    k.setValue('front')
    p.addKnob(k)
    
    k = nuke.Boolean_Knob("crop", "Crop the projections to bbox")
    k.setTooltip("Use this with caution if you use lens distortion that stretches outside of the format")
    p.addKnob(k)
    
    # Add the "occlusion mode" knob. Normally we would only want to project 
    # against the normals.
    k = nuke.Enumeration_Knob("occlusion_mode", "occlusion mode", ['none', 'self', 'world'])
    k.setFlag(nuke.STARTLINE)
    k.setValue('none')
    p.addKnob(k)
    
    result = p.showModalDialog()    
    
    if result == 0:
        return # Canceled
    
    start = p.knobs()["start"].value()
    finish = p.knobs()["finish"].value()
    istep = p.knobs()["step"].value()
    
    frame_numbers = list(range(start, finish, istep))
    
    link = False
    crop = False
    # Make sure we also use the last frame
    if finish not in frame_numbers:
        frame_numbers.append(finish)
    
    if p.knobs()["backwards"].value():
        frame_numbers.reverse()
    if p.knobs()["crop"].value():
        crop = True
    if p.knobs()["link"].value():
        link = True
    
    # This will be called for every project3d node that gets created
    def setup_project3d(node):
      for k in ('occlusion_mode', 'crop', 'project_on'):
        node[k].setValue(p.knobs()[k].value())
    
    group = create_projection_alley(nuke.selectedNode(), frame_numbers, link, setup_project3d)
    group["label"].setValue("Cam prj f: %d to: %d every: %d" % (start, finish, istep))
    group.setName("ProjectionAlley")

def convert_to_dolly():
    """
    Will extract the "translate" channel of a Camera and put it into
    an Axis node. The rotating Camera will be parented underneath the Axis.
    After that you can parent nodal elements (skydomes etc.) under the Axis.
    """
    if not ensure_camera_selected(nuke.selectedNode()):
        return
    
    cam = nuke.selectedNode()

    dolly = nuke.nodes.Axis()
    dolly.setName("DollyMount")

    # Put the dolly next to the camera in the DAG
    ONE_NODE_WIDTH = 82
    dolly['xpos'].setValue(cam['xpos'].getValue() + ONE_NODE_WIDTH)
    dolly['ypos'].setValue(cam['ypos'].getValue())

    # Move the "translate" knob values into the dolly axis.
    # Shortcut way to copy multiparameter knob animations
    # http://forums.thefoundry.co.uk/phpBB2/viewtopic.php?t=4311
    dolly['translate'].fromScript(cam['translate'].toScript()) 
    
    make_camera_nodal(cam)
    cam.setInput(0, dolly)


def make_camera_nodal(cam):
    # Reset the translations of the camera to 0
    cam['translate'].fromScript("0 0 0")
    # Note that the cam is nodal
    cam['label'].setValue(cam['label'].getValue() + " (nodal)")

def make_selected_cam_nodal():
    if not ensure_camera_selected(nuke.selectedNode()):
        return
    make_camera_nodal(nuke.selectedNode())

def create_projector_panel():
    if not ensure_camera_selected(nuke.selectedNode()):
        return
    
    p = nukescripts.panels.PythonPanel("Create a projector")
    
    k = nuke.Boolean_Knob("link", "Link the projector camera to the original")
    k.setFlag(nuke.STARTLINE)
    k.setTooltip("This will create a live setup that will update when the camera keyframes change")
    p.addKnob(k)
    
    k = nuke.Boolean_Knob("create_shader_tree", "Create shader tree (FrameHold + project3d)")
    k.setFlag(nuke.STARTLINE)
    k.setTooltip("will also create a FrameHold and a Project3D to spare even more clicks")
    p.addKnob(k)
    
    result = p.showModalDialog()    
    if result == 0:
        return # Canceled

    # The API called "get value of the field by providing it's UI label" earns the
    # mark of the most fucked up disgusting crap engineering ever (tm)
    do_link = p.knobs()["link"].value()
    do_tree = p.knobs()["create_shader_tree"].value()
    if do_tree:
        create_camera_at_and_shader(nuke.selectedNode(), nuke.frame(), do_link)
    else:
        create_camera_at(nuke.selectedNode(), nuke.frame(), do_link)

    
if nuke.GUI:
    # Inject our own node bar
    toolbar = nuke.menu("Nodes")
    me = toolbar.addMenu( "Projectionist", os.path.join(ICONS_PATH, "projectionist.png"))
    
    # Attach script commands
    me.addCommand("Create a projector from this camera", create_projector_panel, icon = os.path.join(ICONS_PATH, "at.png"))
    me.addCommand("Create projection alley from this camera", create_projection_alley_panel, icon = os.path.join(ICONS_PATH, "alley.png"))
    me.addCommand("Convert this camera to nodal with dolly axis", convert_to_dolly, icon = os.path.join(ICONS_PATH, "nodal.png"))
    me.addCommand("Make this camera nodal at 0", make_selected_cam_nodal, icon = os.path.join(ICONS_PATH, "onlyNodal.png"))
