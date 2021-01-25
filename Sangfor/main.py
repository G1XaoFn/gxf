import paramiko
import textfsm
import sys
import re
import time
import json

device_info = sys.argv[1:]
hostname = "10.12.32.62"
port = 22345
username = "nt"
password = "a.1234.A"
# try:
#     hostname = device_info[0]
#     port = device_info[1]
#     username = device_info[2]
#     password = device_info[3]
# except IndexError:
#     print("参数列表不正确")
#     exit(-1)

member_key = ("device_name","member_pool","member_name","member_port","address","state")
pool_key = ("pool_name","state","lb_method")
sslprofile_key = ("name","server_cert_shang","server_cert_sign","server_cert_pass","cipher",
                  "proto","sess_cache_enable","sess_cache_size","sess_cache_timeout","output_cert_chain_enable",
                  "server_name","server_cert_ecdsa","cli_auth_enable","auth_cert_method",
                  "auth_fail_method","cert_chain_depth","ca_cert","type")
ssl_profile_fail_method_list_key = ("profile_name","fail_method_list_name","auth_fail_errno","fail_method",
                                    "return_user_define_page","type")
vs_key = ("vs_name","ipprotocol","source","destination","destination_port","service","snat_pool","state",
          "vs_type","ssl_profile")
snatpool_key = ("name","isEnable")
persistence_key = ("name","defaultfrom_type","cookie_name","cookie_method","timeout")
monitor_key = ("name","type","interval","timeout","send_string","receive_string","receive_disable_string","reverse",
               "transparent","slow-ramp-time")
cert_key = ("name","type","public_key","private_key","private_key_passwd","valid","key_pass")
service_port_map = {}
ip_group_map = {}
cert_map = {}
profile_cert_map = {}

def ssh_connect(hostname,port,username,password):
    '''
    连接到设备
    :param hostname: 主机名
    :param port: 端口号
    :param username: 用户名
    :param password: 密码
    :return: ssh对象
    '''
    #获得ssh对象
    ssh = paramiko.SSHClient()
    # 自动添加策略，保存服务器的主机名和密钥信息，如果不添加，那么不再本地know_hosts文件中记录的主机将无法连接
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    #连接服务器
    try:
        ssh.connect(hostname, port, username, password)
    except:
        print("无法连接到服务器！")
        exit(-1)
    return ssh

def clear_channel(func):
    '''
    装饰器，负责创建和销毁channel,并清理terminal输出
    :param func:
    :return:
    '''
    def inner(ssh,command):
        # 建立ssh传输通道
        channel = ssh.invoke_shell(width = 1000)
        func(ssh,"\n",channel)
        result = func(ssh,command,channel)
        #关闭ssh通道
        channel.close()
        return result
    return inner

@clear_channel
def ssh_exec_command(ssh,command,channel=None):
    '''
    执行命令列表，并返回结果字典
    :param ssh: ssh对象
    :param command: 命令列表
    :return: 字典 key=命令 value=执行结果
    '''
    #建立ssh传输通道
    #channel = ssh.invoke_shell(width=1000)
    #有序字典
    #result = collections.OrderedDict()
    result = []

    #执行命令列表中的指令
    for cmd in command:
        #发送一条指令
        channel.send(cmd)
        #等待0.1秒，等服务器执行
        time.sleep(0.3)
        #取出服务器返回内容，一次最多取65535个字节
        temResult = channel.recv(65535)
        #判断是否全部返回取出
        while True:
            #先向服务器传一个空格作为标志，当输出结束，回显空格
            channel.send(" ")
            #等待一下
            time.sleep(0.1)
            #再次取数据
            results = channel.recv(65535)
            #判断是否全部取出,全部取出后退出循环
            if results == b' ':
                break
            temResult += results
        #将字符串做一些处理
        #将byte转string
        str = temResult.decode('utf-8')
        #将字符串切成一行一行
        strResult = str.split("\r\n",str.count("\r\n"))
        #最后一行是无意义的标识，删掉
        strResult.pop()
        #删去第一行命令本身，只留下结果
        del strResult[0]
        #将结果加入列表
        result.append(strResult)
    #关闭ssh通道
    #channel.close()
    return result

def ssh_close(ssh):
    '''
    关闭ssh连接
    :param ssh: ssh对象
    :return: none
    '''
    ssh.close

def save_file(result):
    string = ""
    for str in result:
        string += str + "\n"
    with open("sangfor.txt", "w") as file:
        file.write(string)
    tem = []
    for str in result:
        tem.append("#"+str)
        tem.append(str)
    string = ""
    for str in tem:
        string += str + "\n"
    with open("tem_sangfor.txt","w") as file:
        file.write(string)

def read_file():
    with open("tem_sangfor.txt","r") as file:
        return file.read()

def get_snatpool(string):
    with open("snatpool_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(snatpool_key)):
            map[snatpool_key[i]] = tem[i]
        map["device_name"] = hostname
        value.append(map)
    return value

def get_vlan(string):
    with open("vlan_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_vs(string):
    with open("vs_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    get_service(string)
    get_ip_group(string)
    get_cert(string)
    get_profile_cert_map(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(vs_key)):
            map[vs_key[i]] = tem[i]
        map["source"] = "0.0.0.0"
        if map["vs_name"] in ip_group_map.keys():
            map["destination"] = ip_group_map[map["vs_name"]]
        if map["vs_name"] in service_port_map.keys():
            map["destination_port"] = service_port_map[map["vs_name"]]
        if map["state"] == "true":
            map["state"] = "Enabled"
        elif map["state"] == "false":
            map["state"] = "Disabled"
        if re.match(r".*L4",map["vs_type"]):
            map["vs_type"] = "l4"
        elif re.match(r".*L7",map["vs_type"]):
            map["vs_type"] = "l7"
        certs = []
        print(profile_cert_map.keys())
        for profile in map["ssl_profile"]:
            if profile in profile_cert_map.keys():
                certs.append(profile_cert_map[profile])
        map["certs"] = certs
        value.append(map)
    return value

def get_service(string):
    with open("service_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    for str in data:
        service_port_map[str[0]] = str[1]

def get_ip_group(string):
    with open("ip_group_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    for str in data:
        ip_group_map[str[0]] = str[1]

def get_member(string):
    with open("member_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(member_key)):
            map[member_key[i]] = tem[i]
        #对map进行处理
        map["device_name"] = hostname
        map["member_name"] = map["address"] + ":" + map["member_port"]
        if map["state"] == "NODE_ENABLE":
            map["state"] = "Enabled"
        elif map["state"] == "NODE_OFFLINE":
            map["state"] = "Disabled"
        value.append(map)
    return value

def get_pool(string):
    with open("pool_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    member = get_member(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(pool_key)):
            map[pool_key[i]] = tem[i]
        map["device_name"] = hostname
        #当pool中的member的state全不为enabled时，pool_state为Disabled
        state_flag = False
        for mem in member:
            if mem["member_pool"] == map["pool_name"]:
                if mem["state"] == "Enabled":
                    state_flag = True
        if state_flag == True:
            map["state"] = "Enabled"
        else:
            map["state"] = "Disabled"
        value.append(map)
    return value

def get_persistence(string):
    with open("persistence_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(persistence_key)):
            map[persistence_key[i]] = tem[i]
        map["device_name"] = hostname
        value.append(map)
    return value

def get_monitor(string):
    with open("monitor_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(monitor_key)):
            map[monitor_key[i]] = tem[i]
        map["device_name"] = hostname
        value.append(map)
    return value

def get_cert(string):
    with open("cert_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(cert_key)):
            map[cert_key[i]] = tem[i]
        #用换行符替换<%SSL_ENDL%>
        map["public_key"] = map["public_key"].replace("<%SSL_ENDL%>","\n")
        map["private_key"] = map["private_key"].replace("<%SSL_ENDL%>", "\n")
        cert_map[map["name"]] = map["public_key"]
        value.append(map)
    return value

def get_ssl_profile(string):
    with open("sslprofile_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    ssl_profile_fail_method_list = get_ssl_profile_fail_method_list(string)
    value = []
    for tem in data:
        map = {}
        tem_map = {}
        for i in range(len(sslprofile_key)):
            tem_map[sslprofile_key[i]] = tem[i]
        map["profile_name"] = tem_map["name"]
        map["cert_name"] = tem_map["server_cert_shang"]
        if tem_map["name"] in ssl_profile_fail_method_list.keys():
            tem_map["fail_method_list"] = ssl_profile_fail_method_list[map["profile_name"]]
        map["reserved"] = json.dumps(tem_map,ensure_ascii=False)
        value.append(map)
    return value

def get_ssl_profile_fail_method_list(string):
    with open("ssl_profile_fail_method_list_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for tem in data:
        map = {}
        for i in range(len(ssl_profile_fail_method_list_key)):
            map[ssl_profile_fail_method_list_key[i]] = tem[i]
        value.append(map)
    #按照所属的ssl_profile将map分出来
    result = {}
    for tem in value:
        if tem["profile_name"] not in result.keys():
            result[tem["profile_name"]] = []
            result[tem["profile_name"]].append(tem)
        else:
            result[tem["profile_name"]].append(tem)
    return result

def get_profile_cert_map(string):
    profile = get_ssl_profile(string)
    for map in profile:
        if map["cert_name"] in cert_map.keys():
            profile_cert_map[map["profile_name"]] = cert_map[map["cert_name"]]
    return

command = ["ssl_cli export_all\n"]
ssh = ssh_connect(hostname,port,username,password)
result = ssh_exec_command(ssh,command)
save_file(result[0])
file = read_file()
print(get_vlan(file))
print(get_vs(file))
print(get_monitor(file))
print(get_persistence(file))
print(get_snatpool(file))
print(get_cert(file))