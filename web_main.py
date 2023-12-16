import streamlit as st
import pandas as pd
import numpy as np
import yaml
import os
from utils.utils import *
import pandas as pd
from pikpakapi import PikPakApi
import asyncio
    
hide_streamlit_style = """
<style>

#MainMenu {visibility: hidden;}
.stDeployButton {display:none;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)
# Get the directory of the current script
current_directory = os.path.dirname(os.path.abspath(__file__))
def get_current_rss_profile():
    for i,(site, params) in enumerate(anime_rss.items()):
        if i==st.session_state.state:
            return site, params
if st.sidebar.button("主页"):
    st.session_state.state = -1
    st.rerun()
#if anime_rss exist
anime_rss_dir=os.path.join(current_directory, "anime_rss.yaml")
if os.path.exists(anime_rss_dir):
    anime_rss = yaml.load(open(anime_rss_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
    if anime_rss is None:
        anime_rss={}
else:
    anime_rss={}
    yaml.dump(anime_rss, open(anime_rss_dir, "w",encoding='utf-8'))

setting_dir=os.path.join(current_directory, "setting.yaml")
setting=yaml.load(open(setting_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
#display rss list
n_site=len(anime_rss)
for i,(site, params) in enumerate(anime_rss.items()):
    if st.sidebar.button(f"{site}"):
        st.session_state.state = 0

#intial session
if 'session_id' not in st.session_state:
    st.session_state['session_id'] = 0
if 'state' not in st.session_state:
    st.session_state['state'] = -1
# Initialize or get the item_list from session_state
if 'item_list' not in st.session_state:
    st.session_state['item_list'] = []
name=''
rss_name=''
if st.session_state.state == -1:
    main_container = st.container()
    main_container.write("Welcome to the app")
    main_container.write("This is the main page")
    rss_name=st.text_input("Enter your rss name")
    rss_link=st.text_input("Enter your rss link")
    check=st.checkbox("Advanced options")
    rss_addon=None
    rss_expr=None
    if check:
        rss_addon=st.text_input("Enter your rss addon for searching keywords",placeholder='e.g. ?keyword=')
        rss_expr=st.text_input("Enter your rss regular express between keywords", placeholder='e.g. +')
    if st.button("Add"):
        # if rss_name not in anime_rss:
            anime_rss[rss_name]={'rss_link':rss_link,'addon':rss_addon,'expr':rss_expr,'tasks':[]} #personal tasks goes under rss_link
            with open(anime_rss_dir, "w",encoding='utf-8') as f:
                yaml.dump(anime_rss, f,allow_unicode=True)
            
            rss_name=''
            rss_link=''
            st.rerun()
            # st.success('This is a success message!', icon="✅")
    pp_col1, pp_col2 = st.columns([1,1])
    pikpak_username=pp_col1.text_input("Enter your pikpak username")
    pikpak_password=pp_col2.text_input("Enter your pikpak password",type="password")
    ppbutton_col1, ppbutton_col2 = st.columns([3,1])
    if ppbutton_col1.button("Try Login"):
        client = PikPakApi(
                    username=pikpak_username,
                    password=pikpak_password,
                ) 
        try:
            asyncio.run(client.login())
            st.success("Login success")
        except:
            st.error("Login failed")
    
    if ppbutton_col2.button("save to local"):
        setting=yaml.load(open(setting_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
        setting['pikpak_username']=pikpak_username
        setting['pikpak_password']=pikpak_password
        yaml.dump(setting, open(setting_dir, "w",encoding='utf-8'),allow_unicode=True)
        st.success("Saved to local")
    location=st.text_input("Enter your download location",value=setting['location'] if 'location' in setting else '')
    if st.button("save"):
        setting['location']=location
        yaml.dump(setting, open(setting_dir, "w",encoding='utf-8'),allow_unicode=True)
    rerun=st.button("rerun main.py")
    if rerun:
        setting['rerun']=True
        yaml.dump(setting, open(setting_dir, "w",encoding='utf-8'),allow_unicode=True)
        st.rerun()
        
else:
    site, params=get_current_rss_profile()
    rule_name=st.text_input("Enter your rule name")
    rule_keywords=st.text_input("Enter your rule keywords, separate by comma")
    downloaded_episodes=st.text_input("Enter your downloaded episodes, separate by comma (defualt: download all episodes))",value='')
    if st.button("Add"):
        keyword_list=[keyword for keyword in rule_keywords.split(',') if keyword!='']
        episodes=parse_episode([episode for episode in downloaded_episodes.split(',') if episode!=''])
        if len(keyword_list)!=0:
            task={'rule_name':rule_name,'keywords':keyword_list,'update time':None,'downloaded_episodes':episodes,'enable':True}
            anime_rss[site]['tasks'][rule_name]=task
            # st.write(anime_rss)
            with open(anime_rss_dir, "w",encoding='utf-8') as f:
                yaml.dump(anime_rss, f,allow_unicode=True)
            st.rerun()
    # data_editor=st.data_editor({'A':{"n":1,"m":2},"B":{'n':3,'m':4}})
    #reorder
    tasks_content= [rule_content for rule_name,rule_content in anime_rss[site]['tasks'].items()]
    df=pd.DataFrame(tasks_content)
    desired_column_order = ['rule_name','keywords'] + [col for col in df.columns if col not in  ['rule_name','keywords']]
    df = df[desired_column_order]
    st.data_editor(df)

    option = st.selectbox("Select a rule to edit", df['rule_name'])
    if option:
        current_rule_name=option
        rule_name=st.text_input("Rule name",current_rule_name)
        task_col1, task_col2 = st.columns([1,1])
        current_keywords= ','.join(df[df['rule_name']==option]['keywords'].values[0])
        current_episodes=','.join(map(str,df[df['rule_name']==option]['downloaded_episodes'].values[0]))
        
        
        #space taker
        keywords=task_col1.text_input("Keywords",current_keywords)
        episodes=task_col2.text_input("downloaded_episodes",current_episodes)
        if task_col1.button("Update"):
            keyword_list=[keyword for keyword in keywords.split(',') if keyword!='']
            episode_list=[episode for episode in episodes.split(',') if episode!='']
            anime_rss[site]['tasks'][option]['keywords']=keyword_list
            anime_rss[site]['tasks'][option]['downloaded_episodes']=parse_episode(episode_list)
            if rule_name!=option:
                anime_rss[site]['tasks'][option]['rule_name']=rule_name
                anime_rss[site]['tasks'][rule_name]=anime_rss[site]['tasks'].pop(option)
                rename_folder(option,rule_name,location=setting['location'])
            with open(anime_rss_dir, "w",encoding='utf-8') as f:
                yaml.dump(anime_rss, f,allow_unicode=True)
            st.rerun()
        if task_col2.button("Delete"):
            anime_rss[site]['tasks'].pop(option)
            with open(anime_rss_dir, "w",encoding='utf-8') as f:
                yaml.dump(anime_rss, f,allow_unicode=True)
            st.rerun()

    xml= params['rss_link']
    st.write(f"Current rss profile: {xml}")
    bt=rss2title_bt(xml)
    bt_pd=pd.DataFrame(bt).T
    st.dataframe(bt_pd,width=1000)

if st.sidebar.button("refresh"):
    st.session_state.state = 0
    #st.cache.clear()
    st.rerun()
    # main_container.empty()
