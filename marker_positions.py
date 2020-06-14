import PhotoScan

file_path = PhotoScan.app.getSaveFileName("Specify project filename for saving: ")
f = open(file_path, "w")
for chunk in PhotoScan.app.document.chunks:
    for marker in chunk.markers:
        if None == marker.position:
            continue
        pos = chunk.transform.matrix.mulp(marker.position)
        s = "{:s},{:f},{:f},{:f}\n".format(marker.label, pos.x, pos.y, pos.z)
        print(s)
        f.write(s)
f.close()
