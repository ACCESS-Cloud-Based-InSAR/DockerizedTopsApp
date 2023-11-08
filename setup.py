from pathlib import Path

from setuptools import find_packages, setup


setup(
    name='isce2_topsapp',
    use_scm_version=True,
    description='Automated ISCE2 TopsApp Processing',
    long_description=(Path(__file__).parent / 'README.md').read_text(),
    long_description_content_type='text/markdown',

    url='https://github.com/dbekaert/DockerizedTopsApp',

    author='David Bekaert, Grace Bato, Marin Govorcin, Andrew Johnston, Joe Kennedy, Charlie Marshak, Simran Sangha and ARIA-JPL',
    author_email='access_cloud_based_insar@jpl.nasa.gov',

    license='Apache-2.0',
    classifiers=[
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],

    python_requires='>=3.8',

    install_requires=[
        'asf_search>=3.0.4',
        'boto3',
        'dateparser',
        'dem_stitcher>=2.1',
        'geopandas',
        'hyp3lib>=1.7',
        'jinja2',
        'lxml',
        'matplotlib',
        'netcdf4',
        'numpy',
        'rasterio',
        'shapely',
        'tqdm',
    ],

    extras_require={
        'develop': [
            'flake8',
            'flake8-import-order',
            'flake8-blind-except',
            'flake8-builtins',
            'ipykernel',
            'jsonschema==3.2.0',
            'notebook',
            'papermill',
            'pytest',
            'pytest-cov',
        ]
    },

    packages=find_packages(),
    include_package_data=True,

    entry_points={
        'console_scripts': [
            'isce2_topsapp = isce2_topsapp.__main__:main',
            'gunw_slc = isce2_topsapp.__main__:gunw_slc',
            'gunw_burst = isce2_topsapp.__main__:gunw_burst',
            'makeGeocube = isce2_topsapp.packaging_utils.makeGeocube:main',
            'nc_packaging = isce2_topsapp.packaging_utils.nc_packaging:main'
        ]
    },

    zip_safe=False
)
