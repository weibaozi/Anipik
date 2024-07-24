import json
from pikpakapi import PikPakApi
import asyncio
from typing import  Dict, List
import time

async def magnet_to_download_url(magnet_links:List[str]=None,client: PikPakApi=None)-> Dict[str, str]:
    if client is None:
        client = PikPakApi(
            username="",
            password="",
        ) 
        await client.login()
    # print(json.dumps(client.get_user_info(), indent=4))
    print("=" * 30, end="\n\n")
    file_ids={}
    download_urls=[]
    # offline_download
    if magnet_links is not None:
        for magnet_link in magnet_links:
            try:
                info=json.dumps(
                    await client.offline_download(
                        magnet_link
                    ),
                    indent=4,
                )
                info=json.loads(info)
                file_id=info['task']['file_id']
                file_ids[magnet_link]=file_id
                #print(file_id)
                #print("=" * 30, end="\n\n")
            except Exception as e:
                print(e)
                continue
        #iterate 5 times to check if the task has been completed
        for i in range(10):

            failed_magnet_links=[] #store failed magnet links
            time.sleep(10+10*i)
            js=json.dumps(await client.offline_list(), indent=4)
            for magnet_link in magnet_links:
                if magnet_link in js:
                    print(f"file id:{file_ids[magnet_link]} has not been completed for {magnet_link}")
                    #file_ids.pop(magnet_link)
                    failed_magnet_links.append(magnet_link)

           # task_magnet_links,task_file_ids=file_ids.keys(),file_ids.values()
            for magnet_link,file_id in file_ids.copy().items():
                #skip failed magnet links
                if magnet_link in failed_magnet_links:
                    continue
                try:
                    js=json.dumps(
                            await client.get_download_url(file_id), indent=4
                        )
                    #parse js
                    js=json.loads(js)
                    download_urls.append((js['name'],js['web_content_link']))
                    file_ids.pop(magnet_link)
                except Exception as e:
                    print(e)
                    continue
            #if still task remaining
            if len(file_ids)==0:
                break
            print("task has not been completed, retrying...")
    return download_urls


if __name__ == "__main__":
    urls=['magnet:?xt=urn:btih:cdd228527015a84768e8a4f6e47469b3f29b9e8c&tr=http://open.acgtracker.com:1096/announce',
'magnet:?xt=urn:btih:088ae9511c254dae7fdc310f2396930611861e1c&tr=http://open.acgtracker.com:1096/announce',
'magnet:?xt=urn:btih:30bc227ed8d609336d49a0eae6b65a39b82ec775&tr=http://open.acgtracker.com:1096/announce']
    download_urls=asyncio.run(magnet_to_download_url(magnet_links=urls))
    print(download_urls)
