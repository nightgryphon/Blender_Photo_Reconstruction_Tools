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
from mathutils import Vector, Matrix
import bpy_extras
from bpy_extras.object_utils import world_to_camera_view
import os
from xml.etree import ElementTree as ET
import numpy as np
import bmesh
import csv
import measureit
from addon_utils import check,paths,enable


addon_keymaps = []

def get_bg_image(camera):
    bg = None
    for bg_image in camera.data.background_images:
        if bg_image.image:
            if bg_image.image.name == camera.name:
                bg = bg_image
                break
    return bg

    
    
# -----------------------------------------------------------------
def show_camera(scene, cam, pivot = False):
    cam.data.show_background_images = True
    cam.data.show_limits = False
    cam.data.show_passepartout = False
    cam.data.show_name = True
    cam.hide_set(False)
    scene.camera = cam
    print('Switching to camera: '+cam.name)
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


# -----------------------------------------------------------------
def rotate_2d(xy, radians):
    """rotate a point around the origin (0, 0)."""
    x, y = xy
    xx = x * math.cos(radians) + y * math.sin(radians)
    yy = -x * math.sin(radians) + y * math.cos(radians)

    return xx, yy

# -----------------------------------------------------------------
def adjust_render_resolution(cam):        
    try:
        f = cam.data['f']
        bg = get_bg_image(cam)
        if bg:
            # TODO adjust camera to fit rotated image
            # image first fit to camera (bg_image.frame_method) than rotate
            # how to adjust render resolution to fit _rotated_ image which size depend on render resolution???
            # how to calc FOV for such camera????
            #
            """
            a = rotate_2d([bg.image.size[0],bg.image.size[1]], bg.rotation)
            b = rotate_2d([-bg.image.size[0],bg.image.size[1]], bg.rotation)
            w = max(abs(a[0]), abs(b[0]))
            h = max(abs(a[1]), abs(b[1]))
            print('{:f} x {:f}'.format(w,h))
            bpy.context.scene.render.resolution_x = w
            bpy.context.scene.render.resolution_y = h
            cam.data.angle = 2*math.atan(w/2/f)
            """
            if ('rotate_hack' in cam.data) and (cam.data['rotate_hack']):
                bpy.context.scene.render.resolution_x = bg.image.size[1]
                bpy.context.scene.render.resolution_y = bg.image.size[0]
                bg.scale= bg.image.size[1]/bg.image.size[0]
            else:
                bpy.context.scene.render.resolution_x = bg.image.size[0]
                bpy.context.scene.render.resolution_y = bg.image.size[1]
                bg.scale=1
            # bg_image.frame_method = CROP
            # camera.sensor_fit = auto 
            cam.data.angle = 2*math.atan(max(bg.image.size)/2/f)
            return True
        
    except KeyError:
        print('No F for camera '+cam.name)
        return False
        
    return False
        

# -----------------------------------------------------------------
def get_selected_vertices():
    if bpy.context.active_object and bpy.context.active_object.type == 'MESH':
        obj = bpy.context.active_object
        mat_world = obj.matrix_world

        mode = obj.mode
        # we need to switch from Edit mode to Object mode so the selection gets updated
        bpy.ops.object.mode_set(mode='OBJECT')
        selectedVerts = [mat_world @ v.co for v in obj.data.vertices if v.select]
        # back to whatever mode we were in
        bpy.ops.object.mode_set(mode=mode)
    
        return selectedVerts
    else:
        return []


# -----------------------------------------------------------------
def is_visible(verts_co, cam):
    scene = bpy.context.scene
    cs, ce = cam.data.clip_start, cam.data.clip_end
    res = False
    
    adjust_render_resolution(cam)
    
    for v in verts_co:
        co_ndc = world_to_camera_view(scene, cam, v)
        #check wether point is inside frustum
        if (0.0 < co_ndc.x < 1.0 and
            0.0 < co_ndc.y < 1.0 and
            cs < co_ndc.z):
#            cs < co_ndc.z <  ce):
                res = True
                break
            
    return res

            
# -----------------------------------------------------------------
nav_last_dir = 'unknown'
nav_loop_filter = []    

class Recon_SwitchCamera(bpy.types.Operator):
    bl_idname = "reconstruction.switch_cam"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Change Camera"         # Display name in the interface.
#    bl_options = {'REGISTER'}
#    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        items=[('next', "Next camera", ""),
               ('prev', "Prev caamera", ""),
               ('showcam', "Show caameras", ""),
               ('refresh', "Refresh", "")
               ],
        name="Direction", 
        default='next',
        options={'HIDDEN'} 
        )
        
    def execute(self, context):        # execute() is called when running the operator.
        global nav_last_dir
        global nav_loop_filter

        def cam_index(aname):
            for index, item in enumerate(cams):
                if aname == item.name:
                    break
            else:
                index = -1
                
            return index
        
        settings = context.scene.recon_settings
        print('Direction: {:s}'.format(self.direction))

        scene = context.scene

        if self.direction == 'refresh':
            if scene.camera:
                show_camera(scene, scene.camera, False)
            return {'FINISHED'}

        cams = [obj for obj in scene.objects if obj.type == 'CAMERA']
        print('Cams total: {:d}'.format(len(cams)))

        if self.direction == 'showcam':
            for item in cams:
                item.hide_set(False)
            return {'FINISHED'}


        # loop filter
        if not settings.nav_sort_mode in ['none']:
            print('Last direction {:s}'.format(nav_last_dir))
            print(nav_loop_filter)
            if nav_last_dir == self.direction:
                cams = list(filter(lambda c: not c.name in nav_loop_filter, cams))
                print('Cams loop filter: {:d}'.format(len(cams)))
            else:
                nav_loop_filter = []
             
        nav_last_dir = self.direction
                            
        # visible filter
        sel = False
        if settings.nav_filter_visible:
            if not sel:
                sel = get_selected_vertices()
            if sel:
                cams = list(filter(lambda c: is_visible(sel, c) , cams))
                # restore sensor for current camera
                if scene.camera:
                    adjust_render_resolution(scene.camera)
                print('Cams selected filter: {:d}'.format(len(cams)))


        if scene.camera and 0 <= cam_index(scene.camera.name) < len(cams):
            nav_loop_filter.append(scene.camera.name)

            # angle filter
            cam_direction = scene.camera.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
            if settings.nav_filter_angle_enable:            
                cams = list(filter(lambda c: math.degrees(cam_direction.angle( c.matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0)) )) < settings.nav_filter_angle , cams))
                print('Filter angle: {:d}'.format(len(cams)))
                print('Cams angle filter: {:d}'.format(len(cams)))

            # distance filter
            if settings.nav_filter_distance_enable:            
                cams = list(filter(lambda c: (scene.camera.location - c.location).length < settings.nav_filter_distance , cams))
                print('Filter distance: {:d}'.format(len(cams)))
                print('Cams distance filter: {:d}'.format(len(cams)))

            # sort modes
            if settings.nav_sort_mode == 'distance':                
                m = scene.camera.matrix_world.inverted()
                cams.sort(key=lambda c: math.copysign( (c.location - scene.camera.location).length, (m @ c.location).x) )
                
            if settings.nav_sort_mode == 'camx':
                m = scene.camera.matrix_world.inverted()
                cams.sort(key=lambda c:  (m @ c.location).x )

            if settings.nav_sort_mode == 'camy':
                m = scene.camera.matrix_world.inverted()
                cams.sort(key=lambda c:  (m @ c.location).y )

            if settings.nav_sort_mode == 'camz':
                m = scene.camera.matrix_world.inverted()
                cams.sort(key=lambda c:  (m @ c.location).z )


            # find current camera index
            index = cam_index(scene.camera.name)
            print('Current camera index: {:d}'.format(index))
                
            if index>=0:
                if self.direction == 'prev':
                    index -= 1
                else:
                    index += 1
                    if index >= len(cams):
                        index = -1

            print('Next camera index: {:d}'.format(index))
            if 0 <= index < len(cams):
                new_cam_direction = cams[index].matrix_world.to_quaternion() @ Vector((0.0, 0.0, -1.0))
                print('Angle diff {:f}'.format(math.degrees(cam_direction.angle(new_cam_direction))))
                print('Distance {:f}'.format( (cams[index].location - scene.camera.location).length ))
            
        else:
            # no camera selected or current camera does not fit filters => jump to first matching cam
            index = 0

                    
        if 0 <= index < len(cams):
            view_target = False
            if settings.nav_center_selected:
                if not sel:
                    sel = get_selected_vertices()
                if sel:
                    view_target = sum(sel, Vector()) / len(sel)
                    #view_target = bpy.context.active_object.matrix_world @ view_target

            if settings.nav_hide_other:
                for obj in scene.objects:
                    if obj.type == 'CAMERA':
                        obj.hide_set(True)
            
            show_camera(scene, cams[index], view_target)

            bg_image = get_bg_image(cams[index])
            if bg_image:
                bg_image.alpha = settings.nav_alpha

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


# -----------------------------------------------------------------
def update_alpha(self, context):
#    print(self["nav_alpha"])
#    settings = bpy.context.scene.recon_settings
#    settings["nav_alpha"] = value
    
    camera = bpy.context.scene.camera
    if camera:
        bg_image = get_bg_image(camera)
        if bg_image:
            settings = bpy.context.scene.recon_settings
            bg_image.alpha = settings.nav_alpha
    

# -----------------------------------------------------------------
def rotate_cam(camera, angle):
    if camera:
        bg = get_bg_image(camera)
        if bg:
            bg.rotation -= math.radians(angle)
            camera.rotation_mode = 'AXIS_ANGLE' # adjust euler rotation center to camera position for ZXY mode
#            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            camera.rotation_mode = 'ZXY'
            camera.rotation_euler[2] += math.radians(angle)
            return True
    return False


# -----------------------------------------------------------------
class Recon_RotateCamera(bpy.types.Operator):
    bl_idname = "reconstruction.rotate_cam"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Rotate camera"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}
    bl_options = {'REGISTER', 'UNDO'}

    angle: bpy.props.FloatProperty(
        name='Angle (d)', 
        description = 'Angle to rotate camera',
        default = 0,
        soft_min=-180, 
        soft_max=180
        )
        
    rotate_hack: bpy.props.BoolProperty(
        name="Toggle rotated img hack",
        description="Hack rotated images fit. Swap W/H and scale", 
        default=False,
#        options={'HIDDEN'} 
        )
        
    def execute(self, context):        # execute() is called when running the operator.
        scene = context.scene
        camera = scene.camera

        if rotate_cam(camera, self.angle):
            #fit sensor
            if self.rotate_hack:
                if ('rotate_hack' in camera.data) and (camera.data['rotate_hack']):
                    camera.data['rotate_hack'] = 0
                else:
                    camera.data['rotate_hack'] = 1

            adjust_render_resolution(camera)


        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



# -----------------------------------------------------------------
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


# -----------------------------------------------------------------
class Recon_ToggleMesh(bpy.types.Operator):
    bl_idname = "reconstruction.toggle_mesh"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Toggle Mesh"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    def execute(self, context):        # execute() is called when running the operator.
        settings = context.scene.recon_settings

        if settings.ref_mesh in bpy.data.objects.keys():
            obj = bpy.data.objects[settings.ref_mesh]
            obj.hide_set( not obj.hide_get())

        if settings.ref_mesh in bpy.data.collections.keys():
            col = bpy.data.collections[settings.ref_mesh]
            col.hide_viewport = not col.hide_viewport

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



# -----------------------------------------------------------------
class Recon_Orientations(bpy.types.Operator):
    bl_idname = "reconstruction.orientations_tool"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Save camera orientation"         # Display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    cmd: bpy.props.EnumProperty(
        items=[('create', "Create orientation from view", ""),
               ('switch', "Switch to camera", ""),
               ],
        name="Command", 
        default='create',
        options={'HIDDEN'} 
        )

    def do_create(self, context):        # execute() is called when running the operator.

        scene = context.scene
        cam = scene.camera

        show_camera(scene, cam)
        screen_areas = [
            area for area in bpy.context.screen.areas
            if area.type == 'VIEW_3D'
        ]

        #ToDo: switch to camera view and back
        print('Orientation for '+cam.name)
        bpy.ops.transform.create_orientation(name = cam.name, use_view=True, use=True, overwrite = True)
        bpy.context.scene.transform_orientation_slots[0].type = cam.name

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


    def do_switch(self, context):        # execute() is called when running the operator.

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


    def execute(self, context):        # execute() is called when running the operator.
        # dispatch command
        func = getattr(self, 'do_'+self.cmd)
        func(context)

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



# -----------------------------------------------------------------
class Recon_ImportImages(bpy.types.Operator):
    bl_idname = "reconstruction.load_image"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Load images for selected cameras"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

                
    def execute(self, context):        # execute() is called when running the operator.
        print('Loading...')

        settings = bpy.context.scene.recon_settings
#        camera_angle = 2*math.atan(1280/2/1035.23)

        if settings.image_selected_only:
            sel_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'CAMERA']
            if settings.image_use_current and not bpy.context.scene.camera in sel_objs:
                sel_objs.append(bpy.context.scene.camera)
        else:
            sel_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'CAMERA']
            
        for camera in sel_objs:
            print('Camera {:s} -----------'.format(camera.name))
            try:
                img_path = os.path.join(settings.image_path, camera.name+settings.image_ext)
                print('    Image: {:s}'.format(img_path))

                img = bpy.data.images.load(img_path)
                img.name = camera.name
                img.pack()

                print('    {:d}x{:d}'.format(img.size[0], img.size[1]))

                bg_angle = 0
                bg = None
                if settings.image_clean_existing:
                    for bg_image in camera.data.background_images:
                        if bg_image.image:
                            bpy.data.images.remove(bg_image.image)
                        camera.data.background_images.remove(bg_image)
                else:
                    bg = get_bg_image(camera)
    
                if bg:
                    # image exists
                    bg_angle = bg.rotation
                    if settings.replace_existing:
                        print('    Removing old image')
                        bpy.data.images.remove(bg.image)
                        bg.image = None
                    
                if not bg:
                    bg = camera.data.background_images.new()

                if bg.image:
                    break
                
                print('    Attaching new image')
                bg.show_background_image = True
                if hasattr(bg, 'view_axis'):
                    # only show the background image when looking through the camera (< 2.8)
                    bg.view_axis = 'CAMERA'

                bg.image = img
                bg.display_depth = 'FRONT'
                bg.frame_method = 'CROP'
                bg.alpha = settings.nav_alpha
                bg.rotation = bg_angle
        
                camera.data.lens_unit = 'FOV'
                f = settings.image_f
                if 'f' in camera.data and not settings.image_replace_f:
                    f = camera.data['f']
                camera.data.angle = 2*math.atan(max(img.size)/2/f) # img.size[0]
                camera.data['f'] = f

                camera.data.show_passepartout = False
                camera.data.show_background_images = True
            except:
                print("    Failed!")

        print('Done loading.')
        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



# -----------------------------------------------------------------
class Recon_ImportCameras(bpy.types.Operator):
    bl_idname = "reconstruction.load_camera"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Load cameras from XML"         # Display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

                
    def photoscan2cam(self, world_r, world_t, m_cam):
        m = world_r.to_4x4() @ m_cam
        m.translation += world_t
        return m @ Matrix( ( (1,0,0,0),(0,-1,0,0),(0,0,-1,0),(0,0,0,1) ) )


    def execute(self, context):        # execute() is called when running the operator.
        def import_cam(camera, col):
            name = camera.attrib['label']
            transform = camera.find('transform')
            if transform != None:
                m_cam = Matrix(np.array(transform.text.split(' ')).astype(np.float).reshape((4,4)))
#                print('Camera {:s}'.format(name))
#                print(m_cam)
                
                cam = False
                if name in bpy.context.scene.objects.keys():
                    if settings.cam_update:
                        cam = bpy.context.scene.objects[name]
                        if not settings.cam_use_current or cam != bpy.context.scene.camera:
                            if settings.cam_selected_only and not cam in bpy.context.selected_objects:
                                cam = False
                else:
                    if settings.cam_append:
                        print('Creating new scene camera')
                        cam_cam = bpy.data.cameras.new(name)
                        cam = bpy.data.objects.new(name, cam_cam)
                        #bpy.context.scene.collection.objects.link(cam)
                        col.objects.link(cam)
                        
                if cam:
                    print('Setting up scene camera {:s}'.format(name))
                    cam.matrix_world = self.photoscan2cam(world_r, world_t, m_cam)
                    
#                    print(camera.attrib['sensor_id'])
#                    print(camera.find('orientation').text)
                    s = sensors[camera.attrib['sensor_id']]
                    cam.data.lens_unit = 'FOV'
                    cam.data.angle = 2*math.atan(max(s[0], s[1])/2/s[2])
                    cam.data['f'] = s[2]

                    cam.data['rotate_hack'] = 0
                    bg = get_bg_image(cam)
                    if bg:
                        bg.rotation = 0

                    orientation = camera.find('orientation')
                    if orientation != None:
                        print('Orientation {:s}'.format(orientation.text))
                        # '1' - original
                        if orientation.text == '3':
                            rotate_cam(cam, 180);
                            cam.data['rotate_hack'] = 0

                        if orientation.text == '6':
                            rotate_cam(cam, 90);
                            cam.data['rotate_hack'] = 1

                        if orientation.text == '8':
                            rotate_cam(cam, -90);
                            cam.data['rotate_hack'] = 1

                    if cam == bpy.context.scene.camera:
                        adjust_render_resolution(cam)
            
            
        print('Loading...')

        settings = context.scene.recon_settings

        sel_cams = [obj for obj in bpy.context.selected_objects if obj.type == 'CAMERA']
        
        try:
            col = bpy.data.collections['Cameras']
        except:
            col = bpy.data.collections.new('Cameras')
            bpy.context.scene.collection.children.link(col)

        tree = ET.parse(bpy.path.abspath(settings.cam_file))            
        chunks = tree.findall('chunk')
        for chunk in chunks:
            print('Chunk {:s}'.format(chunk.attrib['label']))
            transform = chunk.find('transform')
            world_t = Vector(np.array(transform.find('translation').text.split(' ')).astype(np.float))
            print(world_t)
            world_r = Matrix(np.array(transform.find('rotation').text.split(' ')).astype(np.float).reshape((3,3)))
            print(world_r)
            
            s = chunk.find('sensors').findall('sensor')
            sensors={}
            for sensor in s:
                resolution = sensor.find('resolution') 
#                print(sensor.find('calibration').attrib['type'])
                sensors[sensor.attrib['id']] = (
                    float(resolution.attrib['width']),
                    float(resolution.attrib['height']),
                    float(sensor.find('calibration').find('f').text),
                    )
            print(sensors)

            cameras = chunk.find('cameras')
            for group in cameras.findall('group'):
                try:
                    grpcol = col.children[group.attrib['label']]
                except:
                    grpcol = bpy.data.collections.new(group.attrib['label'])
                    col.children.link(grpcol)
                    
                for camera in group.findall('camera'):
                    import_cam(camera, grpcol)


            for camera in cameras.findall('camera'):
                import_cam(camera, col)


        print('Done loading.')
        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



# -----------------------------------------------------------------
class Recon_ImportMarkers(bpy.types.Operator):
    bl_idname = "reconstruction.load_markers"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Load markers from XML"         # Display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'

                
    def photoscan2cam(self, world_r, world_t, m_cam):
        m = world_r.to_4x4() @ m_cam
        m.translation += world_t
        return m @ Matrix( ( (1,0,0,0),(0,-1,0,0),(0,0,-1,0),(0,0,0,1) ) )


    def execute(self, context):        # execute() is called when running the operator.
        print('Loading...')

        scene = context.scene
        settings = scene.recon_settings

        try:
            obj = bpy.context.scene.objects["Markers"]
            mesh = obj.data
        except:
            mesh = bpy.data.meshes.new("Markers mesh")
            obj  = bpy.data.objects.new("Markers", mesh)
            bpy.context.collection.objects.link(obj)
            
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.clear()

        # from measureit\measureit_main.py
        if 'MeasureGenerator' not in obj:
            obj.MeasureGenerator.add()

        mp = obj.MeasureGenerator[0]
    
        """
        # load XML
        tree = ET.parse(bpy.path.abspath(settings.markers_file))
        chunks = tree.findall('chunk')
        for chunk in chunks:
            print('Chunk {:s}'.format(chunk.attrib['label']))
            transform = chunk.find('transform')
            world_t = Vector(np.array(transform.find('translation').text.split(' ')).astype(np.float))
            print(world_t)
            world_r = Matrix(np.array(transform.find('rotation').text.split(' ')).astype(np.float).reshape((3,3)))
            print(world_r)
            
            m = chunk.find('markers').findall('marker')
            for marker in m:
                print("Marker {:s}: {:s}".format(marker.attrib['id'], marker.attrib['label']))
                ref = marker.find('reference')
                print(ref)
                if None == ref:
                    continue
                co = Vector([float(ref.attrib['x']), float(ref.attrib['y']), float(ref.attrib['z'])])
                print(co)
        """
        
        # load python exported markers 'marker.position' .CSV
        with open( bpy.path.abspath(settings.markers_file) ) as csvfile:
            rdr = csv.reader( csvfile )
            for i, row in enumerate( rdr ):
                name, x,y,z = row[0:4]
                co = Vector([float(x), float(y), float(z)])
                print("Marker {:s}: {:s}".format(name, str(co) ))
                
                id = len(bm.verts)
                v = bm.verts.new(co)

                mp.measureit_segments.add()
                ms = mp.measureit_segments[mp.measureit_num]
                ms.gltype = 2
                ms.glpointa = id
                ms.glpointb = id
                ms.glarrow_a = scene.measureit_glarrow_a
                ms.glarrow_b = scene.measureit_glarrow_b
                ms.glarrow_s = scene.measureit_glarrow_s
                # color
                ms.glcolor = scene.measureit_default_color
                # dist
                ms.glspace = scene.measureit_hint_space
                # text
                ms.gltxt = name
                ms.glfont_size = scene.measureit_font_size
                ms.glfont_align = scene.measureit_font_align
                ms.glfont_rotat = scene.measureit_font_rotation
                # Add index
                mp.measureit_num += 1

                
                
        bm.to_mesh(obj.data)
        bm.free()

        #for v in obj        
        
        context.area.tag_redraw()

        print('Done loading.')
        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



class Recon_ImportMarkers_panel(bpy.types.Panel):
    bl_label = "Import Markers"
    bl_category = "Photo Reconstruction"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
#        row = layout.row()

        settings = context.scene.recon_settings
        layout.prop(settings, "markers_file")

        layout.separator()

        layout.operator(Recon_ImportMarkers.bl_idname, text="Load Markers")



# -----------------------------------------------------------------
#class Recon_ExportList_item(PropertyGroup):
#    idx: IntProperty()
    
class Recon_Export(bpy.types.Operator):
    bl_idname = "reconstruction.export"        # Unique identifier for buttons and menu items to reference.
    bl_label = "Quick export"         # Display name in the interface.
#    bl_options = {'REGISTER', 'UNDO'}  # Enable undo for the operator.

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'


    cmd: bpy.props.EnumProperty(
        items=[('add', "Add objects", ""),
               ('del', "Delete object", ""),
               ('export', "Export", "")
               ],
        name="Command", 
        default='export',
        options={'HIDDEN'} 
        )

    def do_add(self, context):
        settings = context.scene.recon_settings
        list = settings.export_objects
        names = [itm.name for itm in list]
        
        sel_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']

        if len(sel_objs) == 0:
            sel_objs = [bpy.context.view_layer.objects.active]

        for obj in sel_objs:
            if not obj.name in names:
                itm = list.add()
                itm.name = obj.name


    def do_del(self, context):
        settings = context.scene.recon_settings
        list = settings.export_objects
        
        try:
            list.remove(settings.export_list_idx)
            if settings.export_list_idx > len(list):
                settings.export_list_idx = len(list)-1
        except:
            pass


    def do_export(self, context):
        global export_list_idx
        settings = context.scene.recon_settings
        list = settings.export_objects
        
        # Save selection
        obj_active = bpy.context.view_layer.objects.active
        selection = bpy.context.selected_objects
        mode = obj_active.mode

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')

        hidden = []
        for itm in list:
            obj = context.scene.objects.get(itm.name, None)
            if obj:
                if obj.hide_get():
                    hidden.append(obj.name)
                    obj.hide_set(False)
                obj.select_set(True)
#            print(itm.name)
        try:
            bpy.ops.export_scene.obj(
                filepath = bpy.path.abspath(settings.export_file),
                check_existing = True,
                filter_glob="*.obj;*.mtl", 
                use_selection=True, 
                use_animation=False, 
                use_mesh_modifiers=True, 
                use_edges=True, 
                use_smooth_groups=False, 
                use_smooth_groups_bitflags=False, 
                use_normals=True, 
                use_uvs=False, 
                use_materials=False, 
                use_triangles=True, 
                use_nurbs=False, 
                use_vertex_groups=False, 
                use_blen_objects=True, 
                group_by_object=False, 
                group_by_material=False, 
                keep_vertex_order=False, 
                global_scale=1.0, 
                path_mode='AUTO', 
                axis_forward='Y', 
                axis_up='Z'
                )

            self.report({"INFO"}, 'Export done: {:s}'.format(settings.export_file) )
        except Exception as e:
            if hasattr(e, 'message'):
                self.report({"ERROR"}, e.message)
            else:
                self.report({"ERROR"}, str(e) )

        # restore hidden
        for name in hidden:
            obj = context.scene.objects.get(name, None)
            if obj:
                obj.hide_set(True)
            
        # Restore selection
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selection:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = obj_active
        if not obj_active.hide_get():
            bpy.ops.object.mode_set(mode=mode)



    def execute(self, context):        # execute() is called when running the operator.
        # dispatch command
        func = getattr(self, 'do_'+self.cmd)
        func(context)

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.



class Recon_List_items(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.name)

    def invoke(self, context, event):
        pass   
    
class Recon_Export_panel(bpy.types.Panel):
    bl_label = "Quick Export"
    bl_category = "Photo Reconstruction"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
#        row = layout.row()

        settings = context.scene.recon_settings
        layout.prop(settings, "export_file")

        layout.separator()

        row = layout.row()
        row.template_list("Recon_List_items", "", settings, "export_objects", settings, "export_list_idx")

        col = row.column(align=True)
        col.operator("reconstruction.export", icon='ADD',  text="").cmd = 'add'
        col.operator("reconstruction.export", icon='REMOVE', text="").cmd = 'del'
        
        layout.operator('reconstruction.export', text = 'Export').cmd='export'



# -----------------------------------------------------------------
class Recon_Tools(bpy.types.Operator):
    bl_idname = "reconstruction.tools"
    bl_label = "Tools"
#    bl_options = {'REGISTER', 'UNDO'}

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'


    cmd: bpy.props.EnumProperty(
        items=[ ('set_orientation', "Set object orientation", ""),
                ('measure_edge', 'Measure active edge len', ''),
               ],
        name="Command", 
        default='set_orientation',
        options={'HIDDEN'} 
        )

    def do_set_orientation(self, context):
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            return
        old_mat = obj.matrix_world

        mode = obj.mode
        bpy.ops.object.mode_set(mode='EDIT')

        try:
            new_mat = bpy.context.scene.transform_orientation_slots[0].custom_orientation.matrix.to_4x4()
        except:
            or_save = bpy.context.scene.transform_orientation_slots[0].type
            bpy.ops.transform.create_orientation(name = 'set_orientation_temporary', use_view=False, use=True, overwrite = True)
            new_mat = bpy.context.scene.transform_orientation_slots[0].custom_orientation.matrix.to_4x4()
            bpy.ops.transform.delete_orientation()
            bpy.context.scene.transform_orientation_slots[0].type = or_save
        
        # keep object translation
        new_mat = Matrix.Translation(old_mat.to_translation()) @ new_mat
        k = new_mat.inverted() @ old_mat

        bpy.ops.object.mode_set(mode='OBJECT')

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        for v in bm.verts:
            new_co = k @ v.co.to_4d()
            v.co = new_co.to_3d()
        bm.to_mesh(obj.data)
        bm.free()
            
        bpy.ops.object.mode_set(mode=mode)

        obj.matrix_world = new_mat
        

    def do_measure_edge(self, context):
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            return

        if not 'EDIT' == obj.mode:
            return

        bm = bmesh.from_edit_mesh(obj.data)
        for elem in reversed(bm.select_history):
            if isinstance(elem, bmesh.types.BMEdge):
                bpy.context.window_manager.clipboard = elem.calc_length()
                len = 'Edge length: {:f}'.format(elem.calc_length())
                self.report({"INFO"}, len )
                print( len )
                break
        else:
            self.report({"ERROR"}, 'Please select edge')

    
        bm.free()
            


    def execute(self, context):        # execute() is called when running the operator.
        # dispatch command
        func = getattr(self, 'do_'+self.cmd)
        func(context)

        return {'FINISHED'}            # Lets Blender know the operator finished successfully.


class Recon_Tools_panel(bpy.types.Panel):
    bl_label = "Tools"
    bl_category = "Photo Reconstruction"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
#        row = layout.row()

        settings = context.scene.recon_settings
        
        layout.label(text='Camera orientation')
        layout.operator(Recon_Orientations.bl_idname, text="Create orientation").cmd='create'
        layout.operator(Recon_Orientations.bl_idname, text="Switch to camera").cmd='switch'

        layout.separator()
        layout.label(text='Miscellaneous')
        layout.operator(Recon_Tools.bl_idname, text = 'Set obj orientation').cmd='set_orientation'
        layout.operator(Recon_Tools.bl_idname, text = 'Edge length').cmd='measure_edge'


#--------------------------
class Recon_Settings(bpy.types.PropertyGroup):
    # ----- LOAD IMG -------
    image_path: bpy.props.StringProperty(
        name = 'Images dir',
        description = 'Directory to load camera images from',
        default = os.path.dirname(bpy.data.filepath), 
        maxlen = 1024, 
        subtype = 'DIR_PATH'
        )

    image_ext: bpy.props.StringProperty(
        name = 'Image ext',
        description = 'Image files extension',
        default = '.jpg', 
        maxlen = 32
        )

    image_f: bpy.props.FloatProperty(
        name='Focal length (px)', 
        description = 'Focal length in pixels',
        default = 1024,
        min=0, 
        soft_max=2048
        )
        
    image_replace_f: bpy.props.BoolProperty(
        name='Overwrite F', 
        description = 'Replace stored focal length',
        default = False
        )

    image_replace_existing: bpy.props.BoolProperty(
        name='Reload images', 
        description = 'Replace already loaded images',
        default = True
        )

    image_clean_existing: bpy.props.BoolProperty(
        name='Clean other images', 
        description = 'Remove all images',
        default = True
        )

    image_selected_only: bpy.props.BoolProperty(
        name="Selected only", 
        description = 'Update only selected cameras',
        default=False,
        )
        
    image_use_current: bpy.props.BoolProperty(
        name="Include current", 
        description = 'Include current camera',
        default=True,
        )
        
    # ---- NAV ----
    nav_alpha: bpy.props.FloatProperty(
        name='Alpha', 
        description = 'Photo transparency',
        default = 0.6,
        min=0, 
        max=1,
#        set=set_alpha
        update=update_alpha
        )
        
    nav_center_selected: bpy.props.BoolProperty(
        name="Center selected", 
        default=True,
#        options={'HIDDEN'} 
        )
        
    nav_hide_other: bpy.props.BoolProperty(
        name="Hide other cameras", 
        default=True,
#        options={'HIDDEN'} 
        )
        
    nav_filter_visible: bpy.props.BoolProperty(
        name="Camera must see selection", 
        default=True,
#        options={'HIDDEN'} 
        )
        
    nav_filter_angle_enable: bpy.props.BoolProperty(
        name="Direction filter", 
        description = 'Do not switch to camera if its angle differs more than specified',
        default=False,
#        options={'HIDDEN'} 
        )
        
    nav_filter_angle: bpy.props.FloatProperty(
        name='Max angle', 
        description = 'Maximum angle between this and next cameras',
        default = 30,
        min=0, 
        soft_max=180
        )
        
    nav_filter_distance_enable: bpy.props.BoolProperty(
        name="Distance filter", 
        description = 'Filter too far cameras',
        default=False,
#        options={'HIDDEN'} 
        )
        
    nav_filter_distance: bpy.props.FloatProperty(
        name='Max distance', 
        description = 'Maximum distance to next camera',
        default = 25,
        min=0, 
        soft_max=100
        )
        
#    nav_sort_distance: bpy.props.BoolProperty(
#        name="Use nearest", 
#        description = 'Switch to nearest camera',
#        default=False,
#        )

    nav_sort_mode: bpy.props.EnumProperty(
        name="Sort", 
        description = 'Camera selection order. WARNING some cameras can be skipped from navigation depending on current camera and sort order',
        items=[('none', "None", ""),
               ('distance', "Nearest", ""),
               ('camx', "Camera X", ""),
               ('camy', "Camera Y", ""),
               ('camz', "Camera Z", ""),
               ],
        default='none',
        )
        
    ref_mesh: bpy.props.StringProperty(
        name = 'Reference model',
        description = 'Reference object or collection to toggle with Ctrl-UP',
        default = 'mesh1', 
        maxlen = 1024, 
        )

    # ----- LOAD CAM -------
    cam_file: bpy.props.StringProperty(
        name = 'File',
        description = 'Cameras XML file',
#        default = os.path.dirname(bpy.data.filepath), 
        maxlen = 1024, 
        subtype = 'FILE_PATH'
        )

    cam_append: bpy.props.BoolProperty(
        name="Append missing", 
        description = 'Append missing cameras',
        default=True,
        )
        
    cam_update: bpy.props.BoolProperty(
        name="Update existing", 
        description = 'Update existing camera positions',
        default=True,
        )
        
    cam_selected_only: bpy.props.BoolProperty(
        name="Selected only", 
        description = 'Update only selected cameras',
        default=True,
        )
        
    cam_use_current: bpy.props.BoolProperty(
        name="Include current", 
        description = 'Include current camera',
        default=True,
        )
        
    # ----- LOAD MARKERS -------
    markers_file: bpy.props.StringProperty(
        name = 'File',
        description = 'Markers XML file',
#        default = os.path.dirname(bpy.data.filepath), 
        maxlen = 1024, 
        subtype = 'FILE_PATH'
        )

    markers_replace: bpy.props.BoolProperty(
        name="Replace existing", 
        description = 'Replace existing markers object',
        default=True,
        )
        
    # ----- EXPORT -------
    export_file: bpy.props.StringProperty(
        name = 'File',
        description = 'Export to',
        maxlen = 1024, 
        subtype = 'FILE_PATH'
        )

    export_objects: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup) #Recon_ExportList_item)
    export_list_idx: bpy.props.IntProperty(
#        default = -1
        )

    

# -----------------------------------------------------------------
class Recon_ImportCameras_panel(bpy.types.Panel):
    bl_label = "Import Cameras"
    bl_category = "Photo Reconstruction"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
#        row = layout.row()

        settings = context.scene.recon_settings
        layout.prop(settings, "cam_file")
        layout.prop(settings, "cam_append")
        layout.prop(settings, "cam_update")
        layout.prop(settings, "cam_selected_only")
        layout.prop(settings, "cam_use_current")

        layout.separator()

        layout.operator('reconstruction.load_camera', text = 'Load cameras')

        layout.separator()
        layout.label(text='Rotate image')

        row = layout.row()

        op = row.operator('reconstruction.rotate_cam', text = '90 CCW')
        op.angle=-90
        op.rotate_hack = 1

        op = row.operator('reconstruction.rotate_cam', text = '90 CW')
        op.angle=90
        op.rotate_hack = 1

        op = layout.operator('reconstruction.rotate_cam', text = 'Flip sensor')
        op.angle=0
        op.rotate_hack = 1


# -----------------------------------------------------------------
class Recon_ImportImages_panel(bpy.types.Panel):
    bl_label = "Import Images"
    bl_category = "Photo Reconstruction"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout
#        row = layout.row()

        settings = context.scene.recon_settings
        layout.prop(settings, "image_path")
        layout.prop(settings, "image_ext")

        layout.prop(settings, "image_replace_existing")
        layout.prop(settings, "image_clean_existing")
        layout.prop(settings, "image_selected_only")
        layout.prop(settings, "image_use_current")

        layout.separator()
        layout.prop(settings, "image_replace_f")
        layout.prop(settings, "image_f")

        layout.separator()
        layout.operator('reconstruction.load_image', text = 'Load images')

        layout.separator()
        layout.label(text='Rotate image')

        row = layout.row()

        op = row.operator('reconstruction.rotate_cam', text = '90 CCW')
        op.angle=-90
        op.rotate_hack = 1

        op = row.operator('reconstruction.rotate_cam', text = '90 CW')
        op.angle=90
        op.rotate_hack = 1

        op = layout.operator('reconstruction.rotate_cam', text = 'Flip sensor')
        op.angle=0
        op.rotate_hack = 1


# -----------------------------------------------------------------
class Recon_Nav_panel(bpy.types.Panel):
    bl_label = "Navigation"
    bl_category = "Photo Reconstruction"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    def draw(self, context):
        layout = self.layout

        settings = context.scene.recon_settings
        layout.prop(settings, "nav_alpha")
        layout.prop(settings, "nav_center_selected")
        layout.prop(settings, "nav_hide_other")
        layout.prop(settings, "nav_sort_mode")
        layout.prop(settings, "nav_filter_visible")
        layout.separator()
        layout.prop(settings, "nav_filter_distance_enable")
        layout.prop(settings, "nav_filter_distance")
        layout.separator()
        layout.prop(settings, "nav_filter_angle_enable")
        layout.prop(settings, "nav_filter_angle")

        layout.separator()
        layout.prop(settings, "ref_mesh")

        layout.separator()
        row = layout.row()
        row.operator(Recon_SwitchCamera.bl_idname, text='Prev').direction='prev'
        row.operator(Recon_SwitchCamera.bl_idname, text='Next').direction='next'
        layout.operator(Recon_SwitchCamera.bl_idname, text='Show cameras').direction='showcam'
        layout.operator(Recon_SwitchCamera.bl_idname, text='Refresh').direction='refresh'


# -----------------------------------------------------------------
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

        layout.operator_context = 'INVOKE_DEFAULT'
#        layout.operator(Recon_ImportImages.bl_idname, text=Recon_ImportImages.bl_label)


# -----------------------------------------------------------------
# -----------------------------------------------------------------
# -----------------------------------------------------------------
def draw_menu(self, context):
    self.layout.menu(Recon_Menu.bl_idname)    

classes = ( Recon_SwitchCamera, Recon_TogglePhoto, Recon_ToggleMesh,
            Recon_Settings, 
            Recon_Nav_panel, 
            Recon_ImportCameras, Recon_ImportCameras_panel,
            Recon_ImportImages, Recon_ImportImages_panel, 
            Recon_ImportMarkers, Recon_ImportMarkers_panel,
            Recon_RotateCamera, 
            Recon_Export, Recon_List_items, Recon_Export_panel,
            Recon_Orientations,
            Recon_Tools, Recon_Tools_panel,
            Recon_Menu)


# https://blenderartists.org/t/check-if-add-on-is-enabled-using-python/522226
def get_all_addons(display=False):
    """
    Prints the addon state based on the user preferences.
    """
    import sys


    # RELEASE SCRIPTS: official scripts distributed in Blender releases
    paths_list = paths()
    addon_list = []
    for path in paths_list:
        bpy.utils._sys_path_ensure(path)
        for mod_name, mod_path in bpy.path.module_names(path):
            is_enabled, is_loaded = check(mod_name)
            addon_list.append(mod_name)
            if display:  #for example
                print("%s default:%s loaded:%s"%(mod_name,is_enabled,is_loaded))
            
    return(addon_list)


def register():
    addons = get_all_addons()
    addon_dependencies = ['measureit']
    for addon in addon_dependencies:
        if addon in addons:
            is_enabled, is_loaded = check(addon)
            if not is_enabled:
                enable(addon)
        else:
            print("Error Dependency %s missing"%addon)
        
    
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.recon_settings = bpy.props.PointerProperty(type=Recon_Settings)

    bpy.types.VIEW3D_MT_view.append(draw_menu)

    wm = bpy.context.window_manager

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
    kmi = km.keymap_items.new(Recon_Orientations.bl_idname, 'HOME', 'PRESS', ctrl=False, shift=True)
    kmi.properties.cmd='switch'
    addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    bpy.types.VIEW3D_MT_view.remove(draw_menu)

    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.recon_settings

# This allows you to run the script directly from Blender's Text editor
# to test the add-on without having to install it.
if __name__ == "__main__":
    register()