import yaml
import os


# Get the directory of the current script
current_directory = os.path.dirname(os.path.abspath(__file__))
# Construct the path to the file you want to check
file_path = os.path.join(current_directory, "setting.yaml")
#check default setting file:
if not os.path.exists(file_path):
    print("setting.yaml not found, creating one...")
    setting={}
    yaml.dump(setting, open(file_path, "w",encoding='utf-8'))
while True:
    setting=yaml.load(open("setting.yaml", "r",encoding='utf-8'), Loader=yaml.FullLoader)
    break
