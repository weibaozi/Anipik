# 如果你是Python36。请删除37、38、39的pyd文件，其他版本同理
from .WeChatPYAPI import WeChatPYApi

import time
import logging
from queue import Queue
import os
from datetime import datetime
from multiprocessing.dummy import Pool
import yaml
import time
import copy

# 当前目录路径
current_directory = os.path.dirname(os.path.abspath(__file__))
print(current_directory)
notify_queue_dir=os.path.join(current_directory, "wechatbot","message_queue.yaml")

logging.basicConfig(level=logging.INFO)  # 日志器
msg_queue = Queue()  # 消息队列
pool = Pool(5)  # 线程池


def forward(w, msg):
    """转发消息【异步】"""

    # 阻塞等待某些资源下载完毕
    time.sleep(0.5)

    # 如果是图片、视频、文件，要先判断本地是否已经下载好了
    if msg["msg_type"] in [3, 43, 493]:

        # 如果是视频的话，把后缀替换成mp4就是真实路径
        file_path = msg["file_path"].replace(".jpg", ".mp4") if msg["msg_type"] == 43 else msg["file_path"]

        # 1、这里循环是防止某些资源文件过大，还未完全下载完毕
        # 2、严谨点应该控制好循环次数与间隔时间，真的还未下载完（考虑本地网络问题）就放弃该资源吧
        for i in range(5):
            time.sleep(1)
            if os.path.exists(r"{}".format(file_path)):
                break

        # 文件类型会在下载完成之后，更新MsgSvrID，所以要从数据库中查询最新的MsgSvrID
        if msg["msg_type"] == 493:
            db_num = 0
            while True:
                # 查询数据库
                ret = w.select_db(
                    "MSG{}.db".format(db_num),
                    "select MsgSvrID from MSG where StrTalker='{}' AND localId='{}' AND CreateTime='{}';".format(
                        msg["wx_id"],
                        msg["local_id"],
                        msg["time_stamp"]
                    )
                )
                if ret is None:
                    break
                if ret:
                    msg["msg_id"] = ret[0]["MsgSvrID"]
                    break
                db_num += 1

    # 转发消息
    w.forward_msg("filehelper", msg["msg_id"])


def on_message(msg):
    """消息回调，建议异步处理，防止阻塞"""
    print(msg)
    msg_queue.put(msg)


def on_exit(event):
    """退出事件回调"""

    action = event["action"]
    wx_id = event["wx_id"]
    if action == 1:
        print("微信({})：进程结束，请重新启动微信".format(wx_id))
    elif action == 2:
        print("微信({})：已退出登录，请重新登录".format(wx_id))


def main():


    # 实例化api对象【要多开的话就实例化多个《WeChatPYApi》对象】
    w = WeChatPYApi(msg_callback=on_message, exit_callback=on_exit, logger=logging)


    # 启动微信【调试模式可不调用该方法】
    errno, errmsg = w.start_wx()
    # errno, errmsg = w.start_wx(path=os.path.join(BASE_DIR, "login_qrcode.png"))  # 保存登录二维码
    if errno != 0:
        print(errmsg)
        if errmsg != "当前为调试模式，不需要调用“start_wx”":
            return

    # 这里需要阻塞，等待获取个人信息
    while not w.get_self_info():
        time.sleep(2)

    my_info = w.get_self_info()
    print("登陆成功！")
    print(my_info)

    # 拉取列表（好友/群/公众号等）拉取可能会阻塞，可以自行做异步处理
    # 好友列表：pull_type = 1
    # 群列表：pull_type = 2
    # 公众号列表：pull_type = 3
    # 其他：pull_type = 4
    lists = w.pull_list(pull_type=1)
    print(lists)

    # 发送文本消息
    w.send_text(to_wx="wxid_4p5fzh6x73zn11", msg='微信bot已启动')
    time.sleep(1)
    # 处理消息回调【具体根据自己的业务来写，这里只是一个简陋的演示】
    while True:
        notify=yaml.load(open(notify_queue_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
        notify_copy=copy.deepcopy(notify)
        for id, messages in notify_copy.items():
            for message in messages:
                w.send_text(to_wx=id, msg=message)
                notify[id].remove(message)
        notify_check=yaml.load(open(notify_queue_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
        #check if notify changes after read
        if notify_check==notify:
            yaml.dump(notify, open(notify_queue_dir, "w",encoding='utf-8'), allow_unicode=True)
        else:
            new_notify=yaml.load(open(notify_queue_dir, "r",encoding='utf-8'), Loader=yaml.FullLoader)
            #remove sended messages
            for id, messages in notify_copy.items():
                for message in messages:
                    new_notify[id].remove(message)
            yaml.dump(new_notify, open(notify_queue_dir, "w",encoding='utf-8'), allow_unicode=True)
        time.sleep(3)
        


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        os._exit(1)
