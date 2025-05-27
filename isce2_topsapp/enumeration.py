from datetime import datetime, timedelta

import asf_search
import requests


# TODO: support frames crossing antimeridian
# TODO: support ascending frames crossing equator


def _get_frame_by_id(frame_id: int) -> dict:
    for direction in ['ascending', 'descending']:
        # TODO add these files to the repository?
        response = requests.get(f'https://d3g9emy65n853h.cloudfront.net/ARIA_S1_GUNW/{direction}.geojson')
        response.raise_for_status()
        for frame in response.json()['features']:
            if frame['properties']['id'] == frame_id:
                return frame
    raise ValueError(f'No frame found for id {frame_id}')


def _get_wkt_polygon(geometry):
    points = [' '.join(str(coord) for coord in point) for point in reversed(geometry['coordinates'][0])]
    coordinates = ','.join(points)
    return f'polygon(({coordinates}))'


def get_slcs_for_date_and_frame(date: str, frame_id: int) -> list[str]:
    frame = _get_frame_by_id(frame_id)
    results = asf_search.search(
        dataset=asf_search.constants.DATASET.SENTINEL1,
        processingLevel=asf_search.constants.PRODUCT_TYPE.SLC,
        beamMode=asf_search.constants.BEAMMODE.IW,
        polarization=[asf_search.constants.POLARIZATION.VV, asf_search.constants.POLARIZATION.VV_VH],
        flightDirection=frame['properties']['dir'],
        relativeOrbit=frame['properties']['path'],
        intersectsWith=_get_wkt_polygon(frame['geometry']),
        start=datetime.strptime(date, '%Y-%m-%d') + timedelta(minutes=-30),
        end=datetime.strptime(date, '%Y-%m-%d') + timedelta(days=1, minutes=30),
    )
    if len(results) == 0:
        raise ValueError(f'No Sentinel-1 SLCs found for date {date} and frame id {frame_id}.')
    return [result.properties['sceneName'] for result in results]
