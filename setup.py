from pathlib import Path
from setuptools import setup, find_packages

readme = Path(__file__).parent / 'README.md'

setup(
    name='isce2_topsapp',
    # use_scm_version=True,
    description='Automated ISCE2 TopsApp Processing',
    long_description=readme.read_text(),
    long_description_content_type='text/markdown',
    url='https://github.com/dbekaert/DockerizedTopsApp',
    author=('Charlie Marshak, David Bekaert, Grace Bato, Simran Sangha',
            'Joseph Kennedy', 'Brett Buzzunga, and others'
            ),
    author_email='charlie.z.marshak@jpl.nasa.gov',
    license='BSD',
    include_package_data=True,
    classifiers=[
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],

    python_requires='~=3.8',
    package_data={"isce2_topsapp": ["templates/*.xml",
                                    "templates/*.json"]},
    packages=find_packages(
                           exclude=['tmp/', 'tests/']
                          ),
    entry_points={'console_scripts': [
            'isce2_topsapp = isce2_topsapp.__main__:main',
            'makeGeocube = isce2_topsapp.packaging_utils.makeGeocube:main',
            'nc_packaging = isce2_topsapp.packaging_utils.nc_packaging:main'
        ]
    },
    zip_safe=False
)
