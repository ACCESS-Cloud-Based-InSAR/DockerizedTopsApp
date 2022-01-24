import json
from pathlib import PosixPath

from shapely.geometry import Polygon


# Source: https://docs.python.org/3/library/json.html
# and: https://stackoverflow.com/a/3768975
class MetadataEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, PosixPath):
            return str(obj)
        if isinstance(obj, Polygon):
            return obj.__geo_interface__
        return json.JSONEncoder.default(self, obj)
