import requests
import os
import urllib.parse
from typing import Optional, Dict
import re
import bencodepy
import hashlib
import base64
from bs4 import BeautifulSoup
import yaml
import time

download_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
def has_file_extension(url):
    # Regular expression to match a file extension at the end of a URL
    # This regex looks for a period followed by a sequence of alphanumeric characters
    # and underscores at the end of the string
    pattern = r"\.\w+$"
    
    return re.search(pattern, url) is not None

def download(url, location=None, stream=False,filename=None,headers=None):
    """
    Download a file from the given URL and save it to the current directory

    Parameters:
    url (str): The URL of the file to download
    location (str, optional): The location where to save the file, None for not saving (used to get small file like torrent)
    stream (str, optional): If True, the file will be streamed instead of downloaded all at once

    returns:
    bytes: binary file content if location is None, None otherwise

    """
    #check url starts with http
    if not url.startswith('http'):
        url='http://'+url
    try:
        response = requests.get(url, stream=stream,timeout=30,headers=headers)
    except:
        print("file to download file from url:",url)
        return False
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
                try:
                    with open(save_path, 'wb') as file:
                        for data in response.iter_content(chunk_size=4096):
                            file.write(data)
                except Exception as e:
                    print(e)
                    #delete the file if failed to download
                    os.remove(save_path)

            else:
                with open(save_path, 'wb') as file:
                    file.write(response.content)
            # print(f"File downloaded and saved as {save_path}")
            return True
        else:
            return response.content

        
    else:
        print(f"Failed to download the file. Status code: {response.status_code}")
        return None
def extract_episode_number(input_string):
    # Define a regular expression pattern to match the episode number
    patterns = [r'\b(\d{2})\b',r'E(\d{2})\b',r'\b(\d+)\b']
    for pattern in patterns:
        # Use re.search() to find the first match in the string
        match = re.findall(pattern, input_string)
        # Check if a match was found
        # print(match)
        if match:
            episode_number = match[-1]
            # print(episode_number)
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
    response = download(rss_url, headers=download_headers)
    if response is None or type(response) is bool:
        print("Failed to download the RSS file")
        for i in range(10):
            time.sleep(2)
            response = download(rss_url)
            if response is not None and type(response) is not bool:
                break
            else:
                print("Failed to download, retrying...")
        return {}
    # check if the response is xml
    pattern=re.compile(b'^<.*xml')
    if not bool(pattern.match(response)):
        print("The response is not a valid XML file")
        return None
    #prase
    # print(response)
    soup = BeautifulSoup(response, features="xml")
    
    # print(soup)
    # soup = BeautifulSoup(response.text, 'html.parser')
    anime_bt_urls={}
    for item in soup.find_all('item'):
            # print(item.title.text)
            bt=item.find(type="application/x-bittorrent")
            link=item.link.text
            date=item.pubDate.text
            download_url=None
            if bt:
                download_url=bt.get('url')
            #ccurent work for nyaa site
            else:
                try:
                    download_url=item.link.text
                except:
                    print('no url found')
            # print(download_url)
            anime_bt_urls[item.title.text]={'url':download_url,'link':link,'date':date}
    return anime_bt_urls
def send_wechat(message,setting,notify_queue_dir,wechat_id='ALL'):
    notify_queue=yaml.load(open(notify_queue_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
    if notify_queue is None:
        notify_queue={}
    if wechat_id=='ALL':
        for id in setting['wechat_id']:
            if id not in notify_queue:
                notify_queue[id]=[]
            notify_queue[id].append(message)
    else:
        notify_queue[wechat_id].append(message)
    yaml.dump(notify_queue, open(notify_queue_dir, "w",encoding='utf-8'), allow_unicode=True)
    
def safe_load_yaml(file):
    for _ in range(10):
        f=yaml.load(open(file, 'r', encoding='utf-8'), Loader=yaml.FullLoader)
        if f is not None:
            return f

def safe_dump_yaml(data,file):
    for _ in range(10):
        try:
            yaml.dump(data, open(file, "w",encoding='utf-8'), allow_unicode=True)
            return
        except yaml.scanner.ScannerError:
            print('yaml error')
            time.sleep(0.1)
            continue

def rename_folder(old,new,location=''):
    old=os.path.join(location,old)
    new=os.path.join(location,new)
    try:
        if os.path.exists(new):
            #move file under old to new
            for file in os.listdir(old):
                os.rename(os.path.join(old,file),os.path.join(new,file))
            #delete old folder
            os.rmdir(old)
        else:
            os.rename(old,new)
        print('rename success')
    except Exception as e:
        print('rename fail',e)

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