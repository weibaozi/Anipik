import os
import yaml
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
NOTIFY_QUEUE_DIR = os.path.join(CURRENT_DIR, "notify_queue.yaml")
def notify_discord(message,setting,user_id=None,channel_id=None):
    """notify discord user or channel"""
    with open(NOTIFY_QUEUE_DIR, "r+",encoding='utf-8') as f:
        notify_queue=yaml.load(f, Loader=yaml.FullLoader)
        if user_id==None:
            for id in setting['discord_id']['user_id']:
                if id not in notify_queue['discord_user']:
                    notify_queue['discord_user'][id]=[]
                notify_queue['discord_user'][id].append(message)
        else: # only notify if user_id is in the list
            if user_id in setting['discord_id']['user_id']:
                notify_queue['discord_user'][user_id].append(message)
            else:
                print(f"discord user {user_id} not in the list")

        if channel_id==None:
            for id in setting['discord_id']['channel_id']:
                if id not in notify_queue['discord_channel']:
                    notify_queue['discord_channel'][id]=[]
                notify_queue['discord_channel'][id].append(message)
        else:
            if channel_id in setting['discord_id']['channel_id']:
                notify_queue['discord_channel'][channel_id].append(message)
            else:
                print(f"discord channel {channel_id} not in the list")
    yaml.dump(open(NOTIFY_QUEUE_DIR, "w",encoding='utf-8'), allow_unicode=True)
    # yaml.dump(notify_queue, NOTIFY_QUEUE_DIR, allow_unicode=True)

def notify_all(message,setting):
    notify_queue=yaml.load(f, Loader=yaml.FullLoader)
    if setting['wechat'] == True:
        pass
    if setting['discord'] == True:
        notify_discord(message,setting)
        pass
