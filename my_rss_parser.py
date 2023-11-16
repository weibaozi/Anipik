from utils import download
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple, Optional, Union

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
    rss_url = "https://acg.rip/.xml"
    r=rss2title_bt(rss_url)
    print(r)
    
