import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
from shapely import geometry


def generate_burst_request(safe_url, image_number, burst_number, content):
    token = os.environ['EDL_TOKEN']
    urls = {
        'metadata': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata',
        'data': 'https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata',
    }

    url = urls[content]
    headers = {
        'Authorization': f'Bearer {token}',
        'Referer': 't',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = f'zip_url={safe_url}&image_number={image_number}&burst_number={burst_number}'
    return {'url': url, 'headers': headers, 'data': data}


def create_job_xml(reference_safe, secondary_safe, swath, polarization, bbox, do_esd, range_looks, azimuth_looks):
    geocode_list = [
        'merged/phsig.cor',
        'merged/filt_topophase.unw',
        'merged/los.rdr',
        'merged/topophase.flat',
        'merged/filt_topophase.flat',
        'merged/topophase.cor',
        'merged/filt_topophase.unw.conncomp',
    ]

    config = f'''<?xml version="1.0" encoding="UTF-8"?>
    <topsApp>
        <component name="topsinsar">
            <property name="Sensor name">SENTINEL1</property>
            <component name="reference">
                <property name="output directory">reference</property>
                <property name="polarization">'{polarization.lower()}'</property>
                <property name="safe">{reference_safe}</property>
            </component>
            <component name="secondary">
                <property name="output directory">secondary</property>
                <property name="polarization">'{polarization.lower()}'</property>
                <property name="safe">{secondary_safe}</property>
            </component>
            <property name="swaths">[{swath}]</property>
            <property name="range looks">7</property>
            <property name="azimuth looks">3</property>
            <property name="region of interest">{bbox}</property>
            <property name="do denseoffsets">True</property>
            <property name="do ESD">{do_esd}</property>
            <property name="do unwrap">True</property>
            <property name="unwrapper name">snaphu_mcf</property>
            <property name="geocode list">{geocode_list}</property>
        </component>
    </topsApp>
    '''
    return config


def reformat_gcp(point):
    attribs = ['line', 'pixel', 'latitude', 'longitude', 'height']
    values = {}
    for attrib in attribs:
        values[attrib] = float(point.find(attrib).text)
    return values


def create_gcp_df(annotation):
    points = annotation.findall('.//{*}geolocationGridPoint')
    gcp_df = pd.DataFrame([reformat_gcp(x) for x in points])
    gcp_df = gcp_df.sort_values(['line', 'pixel']).reset_index(drop=True)
    return gcp_df


def create_geometry(gcp_df, burst_index, lines_per_burst):
    first_line = gcp_df.loc[gcp_df['line'] == burst_index * lines_per_burst, ['longitude', 'latitude']]
    second_line = gcp_df.loc[gcp_df['line'] == (burst_index + 1) * lines_per_burst, ['longitude', 'latitude']]
    x1 = first_line['longitude'].tolist()
    y1 = first_line['latitude'].tolist()
    x2 = second_line['longitude'].tolist()
    y2 = second_line['latitude'].tolist()
    x2.reverse()
    y2.reverse()
    x = x1 + x2
    y = y1 + y2
    footprint = geometry.Polygon(zip(x, y))
    centroid = tuple([x[0] for x in footprint.centroid.xy])
    return footprint, footprint.bounds, centroid


def get_bounding_box(annotation_path, burst_index):
    annotation = ET.parse(annotation_path).getroot()
    lines_per_burst = int(annotation.findtext('.//{*}linesPerBurst'))
    points = annotation.findall('.//{*}geolocationGridPoint')

    gcp_df = create_gcp_df(points)
    print(gcp_df)
    bounds = create_geometry(gcp_df, burst_index, lines_per_burst)[1]
    return bounds


if __name__ == '__main__':
    home_dir = Path('.') / 'isce2_bursts'
    reference = ''
    secondary = ''
    filename = (
        './filename/burst_script/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.SAFE/'
        'annotation/s1a-iw2-slc-vh-20200604t022253-20200604t022318-032861-03ce65-002.xml'
    )
    burst_index = 1  # we're 1 indexed most of the time
    swath = 2

    if not home_dir.exists():
        home_dir.mkdir()

    # TODO
    # download_metadata()
    # download_data()

    bounds = get_bounding_box(filename, burst_index - 1)  # 0 indexed
    print(bounds)
