import bot
import os
import yaml
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

if __name__ == '__main__':
    setting=yaml.load(open(os.path.join(ROOT_DIR,"setting.yaml"), "r",encoding='utf-8'), Loader=yaml.FullLoader)
    TOKEN=setting['discord_token']
    # print(os.getcwd())
    # print(ROOT_DIR)
    bot.run_bot(TOKEN)