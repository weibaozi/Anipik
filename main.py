import streamlit as st
import pandas as pd
import numpy as np
import yaml
hide_streamlit_style = """
<style>

#MainMenu {visibility: hidden;}
.stDeployButton {display:none;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

if st.sidebar.button("主页"):
    st.session_state.state = 0
    st.rerun()

anime_rss = yaml.load(open("anime_rss.yaml", "r",encoding='utf-8'), Loader=yaml.FullLoader)
n_site=len(anime_rss)
for i,(site, rules) in enumerate(anime_rss.items()):
    if st.sidebar.button(site):
        st.session_state.state = i+1

#intial session
if 'session_id' not in st.session_state:
    st.session_state['session_id'] = 0
if 'state' not in st.session_state:
    st.session_state['state'] = 0
# Initialize or get the item_list from session_state
if 'item_list' not in st.session_state:
    st.session_state['item_list'] = []
name=''
rss_name=''
if st.session_state.state == 0:
    main_container = st.container()
    main_container.write("Welcome to the app")
    main_container.write("This is the main page")
    rss_name=st.text_input("Enter your rss name")
    rss_link=st.text_input("Enter your rss link")
    if st.button("Add"):
        if rss_name not in anime_rss:
            anime_rss[rss_name]={rss_link:None}
            with open("anime_rss.yaml", "w",encoding='utf-8') as f:
                yaml.dump(anime_rss, f)
            
            st.session_state.state = 0
            rss_name=''
            rss_link=''
            st.rerun()
            st.success('This is a success message!', icon="✅")
# else:
#     data_editor=st.data_editor()


if st.sidebar.button("refresh"):
    st.session_state.state = 0
    #st.cache.clear()
    st.rerun()
    # main_container.empty()
