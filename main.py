import yaml
import os
from my_rss_parser import rss2title_bt
from pikpakapi import PikPakApi
from pikpak_utils import magnet_to_download_url
import asyncio
from utils import *
import time
from tqdm import tqdm
while True:
    # Get the directory of the current script
    current_directory = os.path.dirname(os.path.abspath(__file__))
    # Construct the path to the file you want to check
    file_path = os.path.join(current_directory, "setting.yaml")
    #check default setting file:
    if not os.path.exists(file_path):
        print("setting.yaml not found, creating one...")
        setting={}
        yaml.dump(setting, open(file_path, "w",encoding='utf-8'))
        setting=yaml.load(open("setting.yaml", "r",encoding='utf-8'), Loader=yaml.FullLoader)
    #check default anime_rss file:
    anime_rss_dir=os.path.join(current_directory,'anime_rss.yaml')
    if not os.path.exists(anime_rss_dir):
        print("anime_rss.yaml not found, creating one...")
        anime_rss={}
        yaml.dump(anime_rss, open(anime_rss_dir, "w",encoding='utf-8'))
    anime_rss=yaml.load(open(anime_rss_dir, 'r'), Loader=yaml.FullLoader)
    #create client
    client = PikPakApi(
                username="guo361270936@gmail.com",
                password="Boa@1225",
            ) 
    download_queue=[]
    #checking tasks
    for rss_name,content in anime_rss.items():
        addon=content['addon']
        expr=content['expr']
        rss_link=content['rss_link']
        tasks=content['tasks']
        for task in tasks:
            rule_name=task['rule_name']
            if task['enable']==False:
                continue
            downloaded_episodes=task['downloaded_episodes']
            keywords=task['keywords']
            #strip to get rid of the space
            clean_keywords = [keyword.strip() for keyword in keywords]
            rss_search_url=rss_link+addon+ expr.join(clean_keywords)
            print(rss_search_url)
            my_parser = rss2title_bt(rss_search_url)
            for title,content in my_parser.items():
                url=content['url']
                #print(title,url)
                episode_number = extract_episode_number(title)
                if episode_number is None:
                    continue
                if episode_number in downloaded_episodes:
                    continue
                if not is_magnet(url):
                    url=torrent_to_magnet(url)
                    if url is None:
                        print('error download url',title)
                        continue
                
                download=asyncio.run(magnet_to_download_url(client=client,magnet_links=[url]))
                if download is None:
                    print('error download url',title)
                    continue
                download_queue.append(download)
                
                downloaded_episodes.append(episode_number)
                break
                    #download(url)
                    #print(filename)
                    #d
            #print(len(my_parser))
    print(anime_rss)
    print(download_queue)
    for i in tqdm(range(600)):
        time.sleep(1)

        
