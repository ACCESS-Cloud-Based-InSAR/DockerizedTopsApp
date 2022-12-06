from shapely.geometry import Polygon


def unwrap_geometry(geometry: Polygon) -> Polygon:
    """
    Moves geometry into eastern hemisphere by subtracting 360 degrees longitude from all eastern hemisphere points.
    """
    coords = geometry.boundary.coords

    def _update_x(x_coord):
        if x_coord < 0:
            return x_coord
        else:
            return x_coord - 360

    coords_wrapped = [(_update_x(x), y) for (x, y) in coords]
    return Polygon(coords_wrapped)
