bl_info = {
    "name": "Photo reconstruction tools",
    "author": "Mikhail Klimushin AKA Night_Gryphon",
    "category": "Mesh",
    "location": "View3D > View > Photo Reconstruction",
    "blender": (2, 80, 0),
    "version": (1, 0),
    "description": "Helper tools for reconstruction by photos",
    "warning": "",
    "wiki_url": "",
}


import bpy
import math
import mathutils
from mathutils import Vector
import bpy_extras
from bpy_extras.object_utils import world_to_camera_view


addon_keymaps = []

def find_bg(camera):
    bg = None
    for bg_image in camera.data.background_images:
        if bg_image.image:
            if bg_image.image.name == camera.name:
                bg = bg_image
                break
    return bg
    
    
def show_camera(scene, cam, pivot = False):
    cam.data.show_background_images = True
    cam.data.show_limits = False
    cam.data.show_passepartout = False
    cam.data.show_name = True
    cam.hide_set(False)
    scene.camera = cam
    print('Camera: '+cam.name)
    r3d = False
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            r3d = area.spaces[0].region_3d
            break

    if r3d:
        r3d.view_perspective = 'CAMERA'
        adjust_render_resolution(cam)

        if pivot:        
            # center view
            r3d.view_camera_offset = [0,0]

            # refresh hack to let region_3d to setup matrices
#            area.tag_redraw()
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    
            # point to view
            c = r3d.perspective_matrix @ Vector(( pivot[0], pivot[1], pivot[2], 1.0))
            if c.w>0:
                c.x = c.x/c.w
                c.y = c.y/c.w
                c.z = c.z/c.w
                c.w = 1.0
               
            # damn you who wrote blender docs for view_camera_offset/view_camera_zoom
            M_SQRT2 = 1.414213562373095145475
            zoom = pow( M_SQRT2 + r3d.view_camera_zoom/50, 2)
            
            r3d.view_camera_offset = [ c.x/zoom, c.y/zoom ]


def adjust_render_resolution(cam):        
    try:
        f = cam.data['f']
        bg = find_bg(cam)
        if bg:
            bpy.context.scene.render.resolution_x = bg.image.size[0]
            bpy.context.scene.render.resolution_y = bg.image.size[1]
            cam.data.angle = 2*math.atan(max(bg.image.size)/2/f)
            return True
        
    except KeyError:
        print('No F for camera '+cam.name)
        return False
        
    return False
        

def get_selected_vertices():
    if bpy.context.active_object and bpy.context.active_object.type == 'MESH':
        mode = bpy.context.active_object.mode
        # we need to switch from Edit mode to Object mode so the selection gets updated
        bpy.ops.object.mode_set(mode='OBJECT')
        selectedVerts = [v.co for v in bpy.context.active_object.data.vertices if v.select]
        # back to whatever mode we were in
        bpy.ops.object.mode_set(mode=mode)
    
        return selectedVerts
    else:
        return []


def is_visible(verts_co, cam):
    scene = bpy.context.scene
    obj = bpy.context.active_object
    mat_world = obj.matrix_world
    cs, ce = cam.data.clip_start, cam.data.clip_end
    res = False
    
    adjust_render_resolution(cam)
    
    for v in verts_co:
        co_ndc = world_to_camera_view(scene, cam, mat_world @ v)
        #check wether point is inside frustum
        if (0.0 < co_ndc.x < 1.0 and
            0.0 < co_ndc.y < 1.0 and
            cs < co_ndc.z):
#            cs < co_ndc.z <  ce):
                res = True
                break
            
    return res

            

class Recon_SwitchCamera(bpy.types.Operator):
    bl_idname = "reconstruction.switch_cam"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Change Camera"         # Display name in the interface.
#    bl_options = {'REGISTER'}

    direction: bpy.props.EnumProperty(
        items=[('next', "Next camera", ""),
               ('prev', "Prev caamera", "")],
        name="Direction", 
        default='next',
#        options={'HIDDEN'} 
        )
        
    only_visible: bpy.props.BoolProperty(
        name="Camera must contain selection", 
        default=True,
#        options={'HIDDEN'} 
        )
        
    center_selected: bpy.props.BoolProperty(
        name="Center selected", 
        default=True,
#        options={'HIDDEN'} 
        )
        
    hide_other: bpy.props.BoolProperty(
        name="Hide other cameras", 
        default=True,
#        options={'HIDDEN'} 
        )
        
        
    def execute(self, context):        # execute() is called when running the operator.
        scene = context.scene
        cams = [obj for obj in scene.objects if obj.type == 'CAMERA']

        for index, item in enumerate(cams):
            item.hide_set
            if scene.camera.name == item.name:
                break
        else:
            index = -1

        if index>=0:
            view_target = False
            sel = False
            if self.only_visible or self.center_selected:
                sel = get_selected_vertices()
                
            if self.center_selected and sel:
                view_target = sum(sel, Vector()) / len(sel)
                view_target = bpy.context.active_object.matrix_world @ view_target

            if self.only_visible and sel:
                if self.direction == 'prev':
                    dir = reversed(range(0,index))
                else:
                    dir = range(index+1, len(cams))
                    
                for i in dir:
                    if is_visible(sel, cams[i]):
                        index = i
                        break
                else:
                    index = -1
            else:
                if self.direction == 'prev':
                    index = index-1
                else:
                    index = index+1
                    if index >= len(cams):
                        index = -1
                    
        if index>=0:
            if self.hide_other:
                for item in cams:
                    item.hide_set(True)
            
            show_camera(scene, cams[index], view_target)

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_TogglePhoto(bpy.types.Operator):
    bl_idname = "reconstruction.toggle_photo"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Toggle Photo"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.

        scene = context.scene
        print(scene.camera.name)

        cams = [obj for obj in scene.objects if obj.type == 'CAMERA']
        
        for index, item in enumerate(cams):
            if scene.camera.name == item.name:
                break
        else:
            index = -1

        if index>=0:
            camera = cams[index]
            print('Toggle: '+camera.name)
            camera.data.show_background_images = not camera.data.show_background_images

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_ToggleMesh(bpy.types.Operator):
    bl_idname = "reconstruction.toggle_mesh"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Toggle Mesh"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.

        obj = bpy.data.objects['mesh1']
        obj.hide_set( not obj.hide_get())

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_SaveOrientation(bpy.types.Operator):
    bl_idname = "reconstruction.save_orientation"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Save camera orientation"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.

        scene = context.scene
        cam = scene.camera

        show_camera(scene, cam)
        screen_areas = [
            area for area in bpy.context.screen.areas
            if area.type == 'VIEW_3D'
        ]

        print('Orientation for '+cam.name)
        bpy.ops.transform.create_orientation(name = cam.name, use_view=True, use=True, overwrite = True)
        bpy.context.scene.transform_orientation_slots[0].type = cam.name
        """
        orient_slot = [
            slot for slot in
            bpy.context.scene.transform_orientation_slots
            if slot.custom_orientation
                and slot.custom_orientation.name == cam.name
        ]
        if orient_slot:
            orient_slot[0].custom_orientation.matrix = screen_areas[0].spaces[0].region_3d.view_matrix.to_3x3() #cam.matrix_world.to_3x3()
        else:
            print('Error: Could not find created transform orientation...')
        """

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_SwitchToOrientation(bpy.types.Operator):
    bl_idname = "reconstruction.camera2orientation"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Switch Camera by Orientation"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.

        scene = context.scene
        name = bpy.context.scene.transform_orientation_slots[0].type
        print('Switching to '+name);
        cams = [obj for obj in scene.objects if obj.type == 'CAMERA']
        for index, item in enumerate(cams):
            if name == item.name:
                break
        else:
            index = -1

        if index>=0:
            show_camera(scene, cams[index])

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_LoadImages(bpy.types.Operator):
    bl_idname = "reconstruction.load_image"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Load images for selected cameras"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.


        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_Menu(bpy.types.Menu):
    bl_label = "Photo Reconstruction"
    bl_idname = "VIEW3D_MT_reconstruction_menu"

    def draw(self, context):
        layout = self.layout
#        layout.label(text="Photo reconstruction tools", icon='WORLD_DATA')

        layout.operator(Recon_SwitchCamera.bl_idname, text='Next camera').direction='next'
        layout.operator(Recon_SwitchCamera.bl_idname, text='Prev camera').direction='prev'
        layout.operator(Recon_TogglePhoto.bl_idname, text=Recon_TogglePhoto.bl_label)
        layout.operator(Recon_ToggleMesh.bl_idname, text=Recon_ToggleMesh.bl_label)
        layout.operator(Recon_SaveOrientation.bl_idname, text=Recon_SaveOrientation.bl_label)
        layout.operator(Recon_SwitchToOrientation.bl_idname, text=Recon_SwitchToOrientation.bl_label)


def draw_menu(self, context):
    self.layout.menu(Recon_Menu.bl_idname)    

def register():
    wm = bpy.context.window_manager


    bpy.utils.register_class(Recon_SwitchCamera)
    bpy.utils.register_class(Recon_TogglePhoto)
    bpy.utils.register_class(Recon_ToggleMesh)
    bpy.utils.register_class(Recon_SaveOrientation)
    bpy.utils.register_class(Recon_SwitchToOrientation)
    bpy.utils.register_class(Recon_Menu)
    bpy.types.VIEW3D_MT_view.append(draw_menu)

    km = wm.keyconfigs.addon.keymaps.new(name = "Window",space_type='EMPTY', region_type='WINDOW')
    kmi = km.keymap_items.new(Recon_SwitchCamera.bl_idname, 'RIGHT_ARROW', 'PRESS', ctrl=True, shift=False)
    kmi.properties.direction='next'
    addon_keymaps.append((km, kmi))

    km = wm.keyconfigs.addon.keymaps.new(name = "Window",space_type='EMPTY', region_type='WINDOW')
    kmi = km.keymap_items.new(Recon_SwitchCamera.bl_idname, 'LEFT_ARROW', 'PRESS', ctrl=True, shift=False)
    kmi.properties.direction='prev'
    addon_keymaps.append((km, kmi))

    km = wm.keyconfigs.addon.keymaps.new(name = "Window",space_type='EMPTY', region_type='WINDOW')
    kmi = km.keymap_items.new(Recon_TogglePhoto.bl_idname, 'DOWN_ARROW', 'PRESS', ctrl=True, shift=False)
    addon_keymaps.append((km, kmi))

    km = wm.keyconfigs.addon.keymaps.new(name = "Window",space_type='EMPTY', region_type='WINDOW')
    kmi = km.keymap_items.new(Recon_ToggleMesh.bl_idname, 'UP_ARROW', 'PRESS', ctrl=True, shift=False)
    addon_keymaps.append((km, kmi))

    km = wm.keyconfigs.addon.keymaps.new(name = "Window",space_type='EMPTY', region_type='WINDOW')
    kmi = km.keymap_items.new(Recon_SwitchToOrientation.bl_idname, 'HOME', 'PRESS', ctrl=False, shift=True)
    addon_keymaps.append((km, kmi))


def unregister():
    bpy.types.VIEW3D_MT_view.remove(draw_menu)
    bpy.utils.unregister_class(Recon_SwitchCamera)
    bpy.utils.unregister_class(Recon_TogglePhoto)
    bpy.utils.unregister_class(Recon_ToggleMesh)
    bpy.utils.unregister_class(Recon_SaveOrientation)
    bpy.utils.unregister_class(Recon_SwitchToOrientation)
    bpy.utils.unregister_class(Recon_Menu)
    
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()