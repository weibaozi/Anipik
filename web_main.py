import streamlit as st
import pandas as pd
import numpy as np
import yaml
import os
from utils import *
from my_rss_parser import *
from bt2magnet import *
import pandas as pd
hide_streamlit_style = """
<style>

#MainMenu {visibility: hidden;}
.stDeployButton {display:none;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def get_current_rss_profile():
    for i,(site, params) in enumerate(anime_rss.items()):
        if i==st.session_state.state:
            return site, params
if st.sidebar.button("主页"):
    st.session_state.state = -1
    st.rerun()
#if anime_rss exist
if os.path.exists("anime_rss.yaml"):
    anime_rss = yaml.load(open("anime_rss.yaml", "r",encoding='utf-8'), Loader=yaml.FullLoader)
    if anime_rss is None:
        anime_rss={}
else:
    anime_rss={}
    yaml.dump(anime_rss, open("anime_rss.yaml", "w",encoding='utf-8'))
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
            with open("anime_rss.yaml", "w",encoding='utf-8') as f:
                yaml.dump(anime_rss, f,allow_unicode=True)
            
            rss_name=''
            rss_link=''
            st.rerun()
            # st.success('This is a success message!', icon="✅")
else:
    site, params=get_current_rss_profile()
    rule_name=st.text_input("Enter your rule name")
    rule_keywords=st.text_input("Enter your rule keywords, separate by comma")
    if st.button("Add"):
        keyword_list=[keyword for keyword in rule_keywords.split(',') if keyword!='']
        if len(keyword_list)!=0:
            task={'rule_name':rule_name,'keywords':keyword_list,'update time':None}
            anime_rss[site]['tasks'].append(task)
            # st.write(anime_rss)
            # with open("anime_rss.yaml", "w",encoding='utf-8') as f:
            #     yaml.dump(anime_rss, f,allow_unicode=True)
            # st.rerun()
    # data_editor=st.data_editor({'A':{"n":1,"m":2},"B":{'n':3,'m':4}})
    st.data_editor(anime_rss[site]['tasks'])
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
