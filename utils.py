import requests
import os
import urllib.parse
from typing import Optional
# def download(url, location=None, stream=False):
#     response = requests.get(url, stream=stream)
#     # Check if the request was successful (status code 200)
#     if response.status_code == 200:
#         # Get the file content
#         if stream:
#             file_content = response.raw
#         else:
#             file_content = response.content
#         return file_content

#     else:
#         print(
#             f"Failed to download the file. Status code: {response.status_code}")
#         return False


def download(url, location=None, stream=False) -> Optional[bytes]:
    """
    Download a file from the given URL and save it to the current directory

    Parameters:
    url (str): The URL of the file to download
    location (str, optional): The location where to save the file, None for not saving (used to get small file like torrent)
    stream (str, optional): If True, the file will be streamed instead of downloaded all at once

    returns:
    bytes: binary file content if location is None, None otherwise

    """
    response = requests.get(url, stream=stream)
    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Get the file name

        filename = os.path.basename(url)
        filename = urllib.parse.unquote(filename)
        save_path = filename
        if location is not None:
            save_path = os.path.join(location, filename)
        # print(f"Saving file to {save_path}")
            if stream:
                with open(save_path, 'wb') as file:
                    for data in response.iter_content(chunk_size=4096):
                        file.write(data)
            else:
                with open(save_path, 'wb') as file:
                    file.write(response.content)
        else:
            return response.content

        # print(f"File downloaded and saved as {save_path}")
        return None
    else:
        # print(f"Failed to download the file. Status code: {response.status_code}")
        return None

if __name__ == "__main__":
    url='https://acg.rip/t/292293.torrent'
    download(url,location='./')