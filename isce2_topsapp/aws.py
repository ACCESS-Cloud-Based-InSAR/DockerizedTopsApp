"""Tools for working with AWS"""

import logging
from mimetypes import guess_type
from pathlib import Path
from typing import Union

import boto3

S3_CLIENT = boto3.client('s3')


def get_tag_set(file_name: str) -> dict:
    if file_name.endswith('.png'):
        file_type = 'browse'
    else:
        file_type = 'product'

    tag_set = {
        'TagSet': [
            {
                'Key': 'file_type',
                'Value': file_type
            }
        ]
    }
    return tag_set


def get_content_type(file_location: Union[Path, str]) -> str:
    content_type = guess_type(file_location)[0]
    if not content_type:
        content_type = 'application/octet-stream'
    return content_type


def upload_file_to_s3(path_to_file: Path, bucket: str, prefix: str = ''):
    key = str(Path(prefix) / path_to_file.name)
    extra_args = {'ContentType': get_content_type(key)}

    logging.info(f'Uploading s3://{bucket}/{key}')
    S3_CLIENT.upload_file(str(path_to_file), bucket, key, extra_args)

    tag_set = get_tag_set(path_to_file.name)

    S3_CLIENT.put_object_tagging(Bucket=bucket, Key=key, Tagging=tag_set)
