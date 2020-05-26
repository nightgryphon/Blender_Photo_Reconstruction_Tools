# Blender Photo Reconstruction Tools

This plugin provide tools to:

- setup images and adjust cameras imported from photogrammetry software like AgiSoft Photo Scan
- easy navigate between all imported cameras using hot keys and automatically filtering cameras for current selection only
- some tools to simplify reconstruction process



## Import cameras from AgiSoft Photo Scan to Blender:

![Imported camera example](https://raw.githubusercontent.com/nightgryphon/Blender_Photo_Reconstruction_Tools/master/doc/Screen1024.png)

At Photo Scan:

- export model to file supporting cameras export like .DAE
- export images: Export -> Undistort Photos, filename template {camera}.{fileext}
- get adjusted camera focal length: Tools -> Camera Calibration -> "Adjusted" tab

At Blender: 

- import model containig cameras
- select cameras you wish to setup
- open "Photo Reconstruction" panel at the rigth side of 3D view (can be folded under [<] thing)
- in "Load Images" section provide folder with saved undistorted photos, focal length for selected cameras
- if you wish to force cameras to update check "Reload images" otherwise only missing images will be loaded


## Navigation
![Navigation panel](https://raw.githubusercontent.com/nightgryphon/Blender_Photo_Reconstruction_Tools/master/doc/NavPanel.png)

Navigate through cameras with Ctrl-Left / Ctrl-Right

### Alpha
Change photo transparency

### Center selected
Put selection center in the middle of viewport

### Hide other cameras
Hide all cameras except the active one

### Sort
Criteria to choose next camera. Keep in mind that 'sorted' camera list is not reversable as it is built for current camera not for scene.

- None: use cameras order within scene data
- Distance: choose closest camera in selected direction
- Camera X/Y/Z: choose camera which have closest X/Y/Z coordinate within current camera space

### Filters
Distance: filter out too large jumps between cameras while navigating  
Angle: filter cameras with view direction too different from current camera  

## Orientation
Change camera orientation with "Photo Reconstruction" panel -> Rotate camera  
If your photo set contain both vertical and horisontal captured photos it can be convenient to rotate such cameras to preserve general scene orientation on screen.  
This effect is achieved by rotating both camera and image. But this also require to adjust render area for such rotated cameras. If camera sensor/image does not fit scene try to use "Navigation panel"->"Refresh" button 

## Other tools:

- Toggle photo visibility with Ctrl-Down
- Toggle imported mesh visibility with Ctrl-Up ("mesh1")
- Save current view orientation with Photo Reconstruction -> Save Orientation
- Switch to camera according selected saved orientation Shift-Home
