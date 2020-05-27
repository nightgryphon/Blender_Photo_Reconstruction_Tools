# Blender Photo Reconstruction Tools

This plugin provide tools to:

- setup images and adjust cameras imported from photogrammetry software like AgiSoft Photo Scan
- easy navigate between all imported cameras using hot keys and automatically filtering cameras for current selection only
- some tools to simplify reconstruction process


![Cover](https://raw.githubusercontent.com/nightgryphon/Blender_Photo_Reconstruction_Tools/master/doc/Cover.png)

## Import cameras from AgiSoft Photo Scan to Blender:

![Imported camera example](https://raw.githubusercontent.com/nightgryphon/Blender_Photo_Reconstruction_Tools/master/doc/Screen1024.png)

There is two camera export options available in Photo Scan:

- Export cameras as .xml
- Export .DAE model with included cameras

An .xml file contain all information regarding cameras including focal length and image orientation. Using .xml file you can update existing cameras.  
The .dae model contains only camera position/orientation so you has to provide focal length manually.  
Both methods work fine but .xml requre less manual setup  

### Workflow
At Photo Scan:

- export model to .XML (File->Export->Export cameras) or .DAE (File->Export->Export model)
- if using .DAE: get adjusted camera focal length: Tools -> Camera Calibration -> "Adjusted" tab  

- export undistorted images: Export -> Undistort Photos, filename template {camera}.{fileext}

At Blender: 

- for .XML: "Photo Reconstruction" panel -> Import camera. Choose .xml file, press "Load cameras"
- for .DAE: import model containig cameras (Axis orientations: Y forward, Z up)  

- At "Photo Reconstruction" panel -> "Load Images" select folder with saved undistorted photos
- For .DAE: set focal length field
- select cameras you wish to setup images or clear "Selected only" box
- if you wish to force cameras to update check "Reload images" otherwise only missing images will be loaded

"Photo Reconstruction" panel is located at the rigth side of 3D view (can be folded under [<] thing)  

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
Criteria to choose next camera. Keep in mind that 'sorted' camera list is not reversable as it is different for each selected camera.

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
