import discord
from responses import *
import time
import asyncio
import os
import yaml
TOKEN =''

current_directory = os.path.dirname(os.path.abspath(__file__))
parent_directory = os.path.dirname(current_directory)
notify_queue_dir=os.path.join(parent_directory,"notify_queue.yaml")

async def send_message(message,user_message,is_private):
    try:
        response=get_response(user_message)
        await message.author.send(response) if is_private else await message.channel.send(response)
    except Exception as e:
        print(e)

def run_bot(TOKEN=TOKEN):
    
    intents=discord.Intents.default()
    intents.members=True
    intents.message_content=True
    client = discord.Client(intents=intents)
    

    @client.event
    async def on_ready():
        print(f'{client.user} has connected to Discord!')
        await notify_send()

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        username=str(message.author.name)
        user_message=str(message.content)
        channel=str(message.channel)
        print(f'{username} : {user_message} ({channel})')

        if user_message[0] == '!':
            command=user_message[1:]
            is_private=isinstance(message.channel,discord.DMChannel)
            await send_message(message,command,is_private)

    #handle notify queue
    async def notify_send():

        while True:
            with open (notify_queue_dir,'r+',encoding='utf-8') as f:
                notify_queue=yaml.load(f, Loader=yaml.FullLoader)
                if notify_queue is None:
                    continue
                for user_id,messages in notify_queue['discord_user'].items():
                    try:
                        user=await client.fetch_user(user_id)
                        while len(messages)>0:
                            await user.send(messages.pop(0))
                    except discord.user.NotFound:
                        print(f"discord user {user_id} not found")
                
                for channel_id,messages in notify_queue['discord_channel'].items():
                    try:
                        channel=await client.fetch_channel(channel_id)
                        while len(messages)>0:
                            await channel.send(messages.pop(0))
                    except discord.channel.NotFound:
                        print(f"discord channel {channel_id} not found")
            yaml.dump(notify_queue, open(notify_queue_dir, "w",encoding='utf-8'), allow_unicode=True)
            await asyncio.sleep(1)

    client.run(TOKEN)