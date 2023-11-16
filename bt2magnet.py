import bencodepy
import hashlib
import base64
import requests
from utils import download
# def download(url):
#     response = requests.get(url)
#     # Check if the request was successful (status code 200)
#     if response.status_code == 200:
#         # Get the file content
#         file_content = response.content
#         return file_content

#     else:
#         print(f"Failed to download the file. Status code: {response.status_code}")
#         return False
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

if __name__ == "__main__":
    torrent_url='https://bangumi.moe/download/torrent/6554353588897300073b846f/[LoliHouse] Paradox Live THE ANIMATION - 06 [WebRip 1080p HEVC-10bit AAC][简繁内封字幕].torrent'
    mag=torrent_to_magnet(torrent_url)
    print(mag)