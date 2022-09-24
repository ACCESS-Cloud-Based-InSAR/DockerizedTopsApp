#!/bin/bash

# for the 2020 Iran EQ:
# reference: https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip
# secondary: https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip
ref_slc_id=S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85
sec_slc_id=S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11
metadata_extractor="https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/metadata"
geotiff_extractor="https://g6rmelgj3m.execute-api.us-west-2.amazonaws.com/geotiff"
zip_url_ref="https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200604T022251_20200604T022318_032861_03CE65_7C85.zip"
zip_url_sec="https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SDV_20200616T022252_20200616T022319_033036_03D3A3_5D11.zip"
# want WH swath 2
image_number=2  # number w/in the SLC; iterates through POL+SWATH
burst_number=3

token=$EDL_TOKEN


START="$(date +%s)"

mkdir -p ${ref_slc_id}.SAFE/measurement ${ref_slc_id}.SAFE/annotation
mkdir -p ${sec_slc_id}.SAFE/measurement ${sec_slc_id}.SAFE/annotation

pushd ${ref_slc_id}.SAFE
curl --get \
     --verbose \
     --data-urlencode "zip_url=${zip_url_ref}" \
     --data-urlencode "image_number=${image_number}" \
     --data-urlencode "burst_number=${burst_number}" \
     --header "Authorization: Bearer ${token}" \
     --location \
     --output ${ref_slc_id}.xml \
     ${metadata_extractor}

curl --get \
     --verbose \
     --data-urlencode "zip_url=${zip_url_ref}" \
     --data-urlencode "image_number=${image_number}" \
     --data-urlencode "burst_number=${burst_number}" \
     --header "Authorization: Bearer ${token}" \
     --location \
     --output ${ref_slc_id}.tif \
     ${geotiff_extractor}
popd

pushd ${sec_slc_id}.SAFE
curl --get \
     --verbose \
     --data-urlencode "zip_url=${zip_url_sec}" \
     --data-urlencode "image_number=${image_number}" \
     --data-urlencode "burst_number=${burst_number}" \
     --header "Authorization: Bearer ${token}" \
     --location \
     --output ${sec_slc_id}.xml \
     ${metadata_extractor}

curl --get \
     --verbose \
     --data-urlencode "zip_url=${zip_url_sec}" \
     --data-urlencode "image_number=${image_number}" \
     --data-urlencode "burst_number=${burst_number}" \
     --header "Authorization: Bearer ${token}" \
     --location \
     --output ${sec_slc_id}.tif \
     ${geotiff_extractor}
popd

DURATION=$[ $(date +%s) - ${START} ]
echo ${DURATION}
