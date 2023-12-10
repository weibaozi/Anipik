# Anipik
这是一个rss订阅从pikpak自动下番的python脚本,可以自定义规则,并且可以通过discord bot进行通知
**Features:**
- [x] RSS feed from anime sites
- [x] custom anime rules(keywords,episodes)
- [x] download through pikpak
- [x] discord notification 

**使用方法**

1. 安装python3.9+
2. 安装依赖库
```
pip install -r requirements.txt
```

1. 在setting.yaml里填写pikpak账号密码和下载路径:


 location: 

 pikpak_password: 

 pikpak_username: 

4. 启动**run main.bat**, **run web.bat**

5. (可选)目前wechatbot无法使用,可以使用discordbot填写token和你的频道channel id后启动**run dcbot.bat**

6. 在默认浏览器打开后填写对应规则,默认带了一个动漫花园和咒术回战的task,可以自行删除

  
