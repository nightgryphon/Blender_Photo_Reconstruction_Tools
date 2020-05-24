# Blender Photo Reconstruction Tools

This plugin provide tools to:

- setup images and adjust cameras imported from photogrammetry software like AgiSoft Photo Scan
- easy navigate between all imported cameras using hot keys and automatically filtering cameras for current selection only
- some tools to simplify reconstruction process



## Import cameras from AgiSoft Photo Scan to Blender:
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


## Tools:

- Navigate through cameras with Ctrl-Left / Ctrl-Right
- Change camera orientation with "Photo Reconstruction" panel -> Rotate camera
- Toggle photo visibility with Ctrl-Down
- Toggle imported mesh visibility with Ctrl-Up
- Save current view orientation with Photo Reconstruction -> Save Orientation
- Switch to camera according selected saved orientation Shift-Home
