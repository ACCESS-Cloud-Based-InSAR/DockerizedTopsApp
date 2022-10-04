import geopandas as gpd
import pandas as pd
from shapely import geometry

# SNWE
b6 = [27.82438514231721, 28.17945871655969, 53.145408078462644, 54.227092838767106]  # True Negative

b7 = [27.658049768305457, 28.013251072911206, 53.11196106344935, 54.19193784300189]  # False Positive

b8 = [27.491831927404057, 27.847161580403135, 53.07855985074144, 54.15684468161031]  # True Positive

b9 = [27.325111859227817, 27.68057097554418, 53.045079513806, 54.1216820813]  # False Positive

# Need to find a way to create this in a way that it only overlaps with b8
bbox = [27.674298288508663, 27.676298288508665, 53.65062458591323, 53.65262458591322]

# OR modify this function
def overlap(box1, box2):
    '''
    Overlapping rectangles overlap both horizontally & vertically
    '''
    hoverlaps = True
    voverlaps = True

    if (box1[2] >= box2[3]) or (box1[3] <= box2[2]):
        hoverlaps = False

    if (box1[1] <= box2[0]) or (box1[0] >= box2[1]):
        voverlaps = False

    return hoverlaps and voverlaps


if __name__ == '__main__':
    polys = []
    for b in [b6, b7, b8, b9, bbox]:
        # SNWE to minx, miny, maxx, maxy
        reformatted = [b[2], b[0], b[3], b[1]]
        poly = geometry.box(*reformatted)
        polys.append(poly)

        print(overlap(b, bbox))

    df = pd.DataFrame({'value': ['b6', 'b7', 'b8', 'b9', 'bbox']})
    gdf = gpd.GeoDataFrame(df, geometry=polys, crs='EPSG:4326')
    gdf.to_file('boxes.geojson')
