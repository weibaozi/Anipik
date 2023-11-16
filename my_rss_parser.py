from requests import get  # noqa
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple, Optional, Union

def rss2title_bt(rss_url) -> Dict[str, str]:
    # rss_url = "https://acg.rip/.xml"
    response = get(rss_url)
    if response.status_code != 200:
        print("Failed to fetch rss")
        return {}
    #prase
    soup = BeautifulSoup(response.text, features="xml")
    # soup = BeautifulSoup(response.text, 'html.parser')
    anime_bt_urls={}
    for item in soup.find_all('item'):
            # print(item.title.text)
            bt=item.find(type="application/x-bittorrent")
            if bt:
                url=bt.get('url')
            
            anime_bt_urls[item.title.text]=url
    # print(anime_bt_urls)
    return anime_bt_urls

if __name__ == "__main__":
    rss_url = "https://acg.rip/.xml"
    r=rss2title_bt(rss_url)
    print(r)
    
