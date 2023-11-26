import requests
import os
import urllib.parse
from typing import Optional, Dict
import re
import bencodepy
import hashlib
import base64
from bs4 import BeautifulSoup
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

def has_file_extension(url):
    # Regular expression to match a file extension at the end of a URL
    # This regex looks for a period followed by a sequence of alphanumeric characters
    # and underscores at the end of the string
    pattern = r"\.\w+$"
    
    return re.search(pattern, url) is not None

def download(url, location=None, stream=False,filename=None):
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
        if filename is None:
            if has_file_extension(url):
                filename = os.path.basename(url)
                filename = urllib.parse.unquote(filename)
            else:
                filename = "downloaded_file"
        save_path = filename
        # print(save_path)
        if location is not None:
            save_path = os.path.join(location, filename)
            #make sure the directory exists
            if not os.path.exists(location):
                try:
                    os.makedirs(location)
                    #FileExistsError
                except:
                    pass
        # print(f"Saving file to {save_path}")
            if stream:
                with open(save_path, 'wb') as file:
                    for data in response.iter_content(chunk_size=4096):
                        file.write(data)
            else:
                with open(save_path, 'wb') as file:
                    file.write(response.content)
            # print(f"File downloaded and saved as {save_path}")
            return True
        else:
            return response.content

        
    else:
        # print(f"Failed to download the file. Status code: {response.status_code}")
        return None
def extract_episode_number(input_string):
    # Define a regular expression pattern to match the episode number
    patterns = [r'\b\d{2}\b',r'\b\d+\b']
    for pattern in patterns:
        # Use re.search() to find the first match in the string
        match = re.search(pattern, input_string)
        # Check if a match was found
        if match:
            episode_number = match.group()
            return episode_number
    return None
    
def is_magnet(url):
    return url.startswith('magnet:?xt=urn:btih:')

def torrent_to_magnet(torrent_url):
    torrent=download(torrent_url)
    # 解码种子文件
    torrent = bencodepy.decode(torrent)

    # 提取info字段并计算其SHA1哈希
    info_hash = hashlib.sha1(bencodepy.encode(torrent[b'info'])).digest()

    # Base32编码哈希值
    encoded_hash = base64.b32encode(info_hash).decode()

    # 构建磁力链接
    magnet_link = f'magnet:?xt=urn:btih:{encoded_hash}'

    return magnet_link
    
def parse_episode(episode_list: list):
    l=set()
    for episode in episode_list:
        episode=str(episode)
        if '-' in episode:
            start,end=episode.split('-')
            l.update(range(int(start),int(end)+1))
        else:
            l.add(int(episode))
    return list(l)

def rss2title_bt(rss_url) -> Dict[str, str]:
    # rss_url = "https://acg.rip/.xml"
    response = download(rss_url)
    if response is None:
        print("Failed to download the RSS file")
        return {}
    #prase
    soup = BeautifulSoup(response, features="xml")
    # soup = BeautifulSoup(response.text, 'html.parser')
    anime_bt_urls={}
    for item in soup.find_all('item'):
            # print(item.title.text)
            bt=item.find(type="application/x-bittorrent")
            if bt:
                url=bt.get('url')
                link=item.link.text
                date=item.pubDate.text
            
            anime_bt_urls[item.title.text]={'url':url,'link':link,'date':date}
    # print(anime_bt_urls)
    return anime_bt_urls

if __name__ == "__main__":
    print("Testing download function...")
    url='https://acg.rip/t/292293.torrent'
    download(url,location='./')
    print("Testing extract_episode_number function...")
    input_string = "【幻月字幕组】【23年日剧】【呛人姐与心机妹】【07】【1080P】【中日双语】 "
    episode_number = extract_episode_number(input_string)
    print(episode_number)
    print("Testing is_magnet function...")
    print(is_magnet('magnet:?xt=urn:btih:cdd228527015a84768e8a4f6e47469b3f29b9e8c&tr=http://open.acgtracker.com:1096/announce'))
    print("Testing torrent_to_magnet function...")
    print(torrent_to_magnet('https://acg.rip/t/292293.torrent'))