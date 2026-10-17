import yaml
import os
# from utils import *
from utils.pikpak_utils import magnet_to_download_url,magnet_to_file_ids
from utils.utils import *
from pikpakapi import PikPakApi
import json
import time
from tqdm import tqdm
import asyncio
import threading
from chatbot.notify import *

global anime_rss
# Get the directory of the current script
current_directory = os.path.dirname(os.path.abspath(__file__))
setting_dir = os.path.join(current_directory, "setting.yaml")
anime_rss_dir = os.path.join(current_directory, 'anime_rss.yaml')
lock = threading.Lock()
setting = yaml.load(open(setting_dir, "r", encoding='utf-8'),
                    Loader=yaml.FullLoader)
notify_queue_dir = os.path.join(
    current_directory, "wechatbot", "notify_queue.yaml")

# def download_helper(download_url,rss_name,task_name,episode_number,location=current_directory):
#     if download(download_url,location=location):
#         print(f"successfully download {task_name} episode {episode_number}")
#         anime_rss
#     pass

# print(message_queue)
intervals = [60, 600, 3600, 7200, 10800]

def download_helper(url,name, download_episodes, episode_number, location=current_directory, stream=False):
    # url = download_url[1]
    # name = download_url[0]
    print(f"Downloading {name}...")
    if download(url, location=location, filename=name, stream=stream):
        print(f"successfully download {name}")
        setting = yaml.load(
            open(setting_dir, "r", encoding='utf-8'), Loader=yaml.FullLoader)
        if setting['discord'] == True:
            notify_discord(
                f"完成下载: {name}", setting)
        with lock:
            download_episodes.append(episode_number)
    else:
        print(f"failed to download {name}")
        #temperory solution, will fix later
        with lock:
            download_episodes.append(episode_number)
async def download_helper_id(download_queue_ids, stream=False,client=None):
    for download_id, (download_episodes, episode_number, location) in download_queue_ids.items():
        
        js=json.dumps(
                        await client.get_download_url(download_id), indent=4
                            )
                        #parse js
        js=json.loads(js)
        url = js['web_content_link']
        name = js['name']
        print(f"Downloading {name}...")
        if download(url, location=location, filename=name, stream=stream):
            print(f"successfully download {name}")
            setting = yaml.load(
                open(setting_dir, "r", encoding='utf-8'), Loader=yaml.FullLoader)
            if setting['discord'] == True:
                notify_discord(
                    f"完成下载: {name}", setting)
            with lock:
                download_episodes.append(episode_number)
        else:
            print(f"failed to download {name}")
            #temperory solution, will fix later
            with lock:
                download_episodes.append(episode_number)
async def download_helper_id_to_tasks(download_queue_ids, stream=False,client=None):
    threads=[]
    for download_id, (download_episodes, episode_number, location) in download_queue_ids.items():
        for i, delay in enumerate(intervals, start=1):
            js = json.dumps(await client.offline_list(), indent=4)
            if download_id in js:
                print(f"[{i}/5] file id:{download_id} has not been completed")
                if i < len(intervals):  # don’t sleep after last attempt
                    if delay >= 60:
                        total = delay // 60   # minutes
                        unit = "min"
                        print(f"Sleeping for {total} {unit}...")
                        for _ in tqdm(range(total), desc="Waiting", unit=unit):
                            await asyncio.sleep(60)
                    else:
                        total = delay         # seconds
                        unit = "s"
                        print(f"Sleeping for {total} {unit}...")
                        for _ in tqdm(range(total), desc="Waiting", unit=unit):
                            await asyncio.sleep(1)
                continue
            else:
                print(f"[{i}/5] file id:{download_id} is completed ✅")
                break
        else:
            print(f"file id:{download_id} not completed after all retries ❌")
            continue
        
        js = json.dumps(await client.get_download_url(download_id), indent=4)
        js=json.loads(js)
        url = js['web_content_link']
        name = js['name']
        thread = threading.Thread(target=download_helper, args=(url, name, download_episodes, episode_number, location, stream))
        threads.append(thread)
    return threads
async def main():

    login = False
    while True:
        # check default setting file:
        if not os.path.exists(setting_dir):
            print("setting.yaml not found, creating one...")
            setting = {}
            yaml.dump(setting, open(setting_dir, "w", encoding='utf-8'),
                    Loader=yaml.FullLoader)
        setting = yaml.load(
            open(setting_dir, "r", encoding='utf-8'), Loader=yaml.FullLoader)

        # check default anime_rss file:
        if not os.path.exists(anime_rss_dir):
            print("anime_rss.yaml not found, creating one...")
            anime_rss = {}
            yaml.dump(anime_rss, open(anime_rss_dir, "w", encoding='utf-8'))
        anime_rss = yaml.load(
            open(anime_rss_dir, 'r', encoding='utf-8'), Loader=yaml.FullLoader)

        # create client
        try:
            json.dumps(client.get_user_info(), indent=4)
            login = True
        except:
            login = False
        while not login:
            if 'pikpak_password' not in setting or 'pikpak_username' not in setting:
                print(
                    "username or password not found in setting.yaml, please fill in your pikpak account")
                setting['pikpak_username'] = input("username:")
                setting['pikpak_password'] = input("password:")
            client = PikPakApi(
                username=setting['pikpak_username'],
                password=setting['pikpak_password'],
                # device_id="GJK-Ry9p"
            )
            # try login 5 times
            for i in range(5):
                try:
                    print("logging in... Current time:", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))) 
                    await client.login()
                    await client.refresh_access_token()
                    # print("test")
                    yaml.dump(setting, open(setting_dir, "w",
                                            encoding='utf-8'), allow_unicode=True)
                    login = True
                    break
                except Exception as e: 
                    print(e)
                    print("login failed, retrying...")
                    #sleep one hour
                    for _ in tqdm(range(125), desc="Timer (2 hour)", unit="min"):
                        # time.sleep(1)
                        await asyncio.sleep(60)
        print("login success")
        if 'location' not in setting:
            location = current_directory
        else:
            location = setting['location']
        download_queue = []
        download_queue_ids = {}
        # checking tasks
        for rss_name, content in anime_rss.items():
            addon = content['addon']
            expr = content['expr']
            rss_link = content['rss_link']
            tasks = content['tasks']
            suffix=content['suffix']
            # print(location,tasks)
            # break
            for _, task in tasks.items():
                rule_name = task['rule_name']
                if task['enable'] == False:
                    continue
                downloaded_episodes = task['downloaded_episodes']
                temp_episodes = downloaded_episodes.copy()
                keywords = task['keywords']
                # strip to get rid of the space at the beginning and end of the string
                clean_keywords = [keyword.strip() for keyword in keywords]
                rss_search_url = addon + expr.join(clean_keywords) + suffix
                # print(rss_search_url)
                my_parser = rss2title_bt(rss_search_url)
                if my_parser is None:
                    print("failed to parse rss")
                    continue
                task_save_dir = os.path.join(location, rule_name)
                for title, content in my_parser.items():
                    url = content['url']
                    # print(title,url)
                    episode_number = extract_episode_number(title)
                    if episode_number is None:
                        continue
                    episode_number = int(episode_number)
                    if episode_number in temp_episodes:
                        # print(f"episode {episode_number} already downloaded")
                        continue
                    if not is_magnet(url):
                        url = torrent_to_magnet(url)
                        if url is None:
                            print('error download url', title)
                            continue
                    print(rule_name, episode_number)
                    try:
                        file_ids = await magnet_to_file_ids(client=client, magnet_links=[url])
                        # print(file_ids)

                    except Exception as e:
                        print(e)
                        print("error download url", title)
                        # await client.refresh_access_token()

                    if url not in file_ids.keys():
                        print('error download url', title)
                        continue
                    # print(download_url)
                    file_id = file_ids[url]
                    download_queue_ids[file_id] = (downloaded_episodes, episode_number, task_save_dir)
                    # thread = threading.Thread(target=download_helper, args=(

                    temp_episodes.append(int(episode_number))

        # await download_helper_id(download_queue_ids, stream=True, client=client)
        threads = await download_helper_id_to_tasks(download_queue_ids, stream=True, client=client)
        #start max threads at a time
        max_threads = 5
        for i in range(0, len(threads), max_threads):  # Step through the list in steps of max_threads
            cur_threads = []
            for thread in threads[i:i+max_threads]:  # Create threads for the next max_threads tasks
                cur_threads.append(thread)
                thread.start()
            
            # Wait for all three threads to complete before moving to the next batch
            for thread in cur_threads:
                thread.join()

        # for thread in download_queue:
        #     thread.start()
        # for thread in download_queue:
        #     thread.join()
        yaml.dump(anime_rss, open(anime_rss_dir, "w",
                encoding='utf-8'), allow_unicode=True)
        # print("all tasks completed")
        # print(download_queue)
        for i in tqdm(range(600)):
            setting = yaml.load(
                open(setting_dir, "r", encoding='utf-8'), Loader=yaml.FullLoader)
            if 'rerun' in setting and setting['rerun'] == True:
                setting['rerun'] = False
                yaml.dump(setting, open(setting_dir, "w",
                        encoding='utf-8'), allow_unicode=True)
                break
            time.sleep(1)

if __name__ == "__main__":
    # print("test")
    asyncio.run(main())