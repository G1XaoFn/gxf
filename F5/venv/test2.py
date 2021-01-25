import paramiko
import textfsm
import re
import time
from http.server import HTTPServer,SimpleHTTPRequestHandler
import urllib.request


profile = {}
vs_key = ("vsName","vsType","partition","vsDestination","destinationDMZIp","vsDestinationPort","vsIpprotocol",
          "vsFullPath","pool_id","persistence_id","snatpool_id","create_time","profiles","vsDescription","vsSource","vsState")
pool_key = ("vsPoolName","partition","vsPoolDescription","vsPoolState","fullpath","vsPoolLbMethod","monitor","create_time")
member_key = ("pool_name","poolMemberName","poolMemberDescription","member_ip","member_port",
              "member_dmz_ip","poolMemberState","disable","down","fullpath","poolMemberCreateTime")
persistence_key = ("name","partition","defaultfrom_type","cookie_name","cookie_method","time_out","create_time")
selfip_key = ("selfip_name", "path","ip_address","netmask","vlan","port_lockdown","traffic_group")
snatpool_key = ("")

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

def clear_terminal(func):
    '''
    装饰器，负责清理终端控制台里剩余的垃圾
    :param func: ssh_exec_command()
    :return:
    '''
    def inner(ssh,command):
        func(ssh," \n")
        func(ssh,command)
    return inner

def open_close_channel(func):
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

@open_close_channel
def ssh_exec_command(ssh,command,channel=None):
    '''
    执行命令列表，并返回结果字典
    :param ssh: ssh对象
    :param commend: 命令列表
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
        time.sleep(0.1)
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

def save_file(result,*args):
    for str in args:
        result.extend(str)
    #先为正则匹配做标记
    tem = []
    for str in result:
        if re.match(r'^ltm',str) != None \
                or re.match(r'^auth',str) != None \
                or re.match(r'^cli', str) != None \
                or re.match(r'^cm', str) != None \
                or re.match(r'^gtm', str) != None \
                or re.match(r'^mgmt', str) != None \
                or re.match(r'^sys', str) != None \
                or re.match(r'^net', str) != None \
                or re.match(r'^util', str) != None \
                or re.match(r'^wom', str) != None:
            tem.append("#a new data table begin:")
        tem.append(str)
    string = ""
    for str in tem:
        string += str + "\n"
    with open("bigip.conf","w") as file:
        file.write(string)

def read_file():
    with open("bigip.conf","r") as file:
        return file.read()

def get_profile(string):
    with open("profile_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
        for i in data:
            if i[0] != i[1]:
                profile[i[0]] = i[1]

def search_profile(name):
    if re.match(r"(.*/)*tcp\s*",name):
        return "l7"
    elif re.match(r"(.*/)*fastL4\s*",name):
        return "l4"
    else:
        try:
            value = profile.get(name)
        except:
            return ""
        if value == None:
            return ""
        return search_profile(value)

def get_vs(string):
    with open("vs_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    get_profile(string)
    #构成list<map>的形式
    value = []
    for i in data:
        map = {}
        for j in range(0,len(vs_key)):
            map[vs_key[j]] = i[j]
        #解决vsType
        profiles = map["profiles"]
        for j in profiles:
            if map["vsType"] != "":
                break
            map["vsType"] = search_profile(j)
        #解决vsState
        if map["vsState"] == "":
            map["vsState"] = "Enabled"
        else:
            map["vsState"] = "Disabled"
        value.append(map)
    return value

def get_pool(string):
    with open("pool_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    member = get_member(string)
    value = []
    for i in data:
        map = {}
        for j in range(0, len(pool_key)):
            map[pool_key[j]] = i[j]
        if map["vsPoolLbMethod"] == "":
            map["vsPoolLbMethod"] = "round-robin"
        state_flag = False
        for mem in member:
            if mem["pool_name"] == map["vsPoolName"]:
                if mem["poolMemberState"] == "Enabled":
                    state_flag = True
        if state_flag == True:
            map["vsPoolState"] = "Enabled"
        else:
            map["vsPoolState"] = "Disabled"
        value.append(map)
    return value

def get_member(string):
    with open("member_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
        data.pop()  #这边要删一行，因为模板中向下填充导致多出一行
    value = []
    for i in data:
        map = {}
        for j in range(0, len(member_key)):
            map[member_key[j]] = i[j]
        if map["down"] != "":
            map["poolMemberState"] = "Forced Offline"
        elif map["disable"] != "":
            map["poolMemberState"] = "Disabled"
        else:
            map["poolMemberState"] = "Enabled"
        map["poolMemberAddress"] = map["member_ip"]
        value.append(map)
    return value

def get_snatpool(string):
    with open("snatpool_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_monitor(string):
    with open("monitor_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_route(string):
    with open("route_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_selfip(string):
    with open("selfip_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_trunk(string):
    with open("trunk_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_vlan(string):
    with open("vlan_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    return data

def get_persistence(string):
    with open("persistence_template") as file:
        re_table = textfsm.TextFSM(file)
        data = re_table.ParseText(string)
    value = []
    for i in data:
        map = {}
        for j in range(0, len(persistence_key)):
            map[persistence_key[j]] = i[j]
        value.append(map)
    return value

def test(hostname,port,username,password,command):
    #----------------------------------------------------------------------------------------------------------
    #从设备上读取配置文件
    execCommand = []
    for str in command:
        execCommand.append(str + "\n")
    ssh = ssh_connect(hostname, port, username, password)
    result = ssh_exec_command(ssh, execCommand)
    ssh_close(ssh)
    #存文件
    time_st = time.time()
    save_file(result[0],result[2],result[1])
    #读文件
    bigip = read_file()
    #----------------------------------------------------------------------------------------------------

    #print(get_vs(bigip))
    #print(get_pool(bigip))
    #print(get_member(bigip))
    # print(get_snatpool(bigip))
    # print(get_monitor(bigip))
    # print(get_route(bigip))
    # print(get_selfip(bigip))
    # print(get_trunk(bigip))
    # print(get_vlan(bigip))
    # print(get_persistence(bigip))
    #time_end = time.time()
    #print(time_end-time_st)


opener = urllib.request.build_opener(urllib.request.HTTPHandler)
with open("persistence_template") as f:
    data=f.read()
request = urllib.request.Request("http://10.12.33.112:8081/conf-manager/v2/api-docs", data=persistence_key)
request.add_header("Content-Type", "application/json")
request.get_method = lambda:"PUT"
url = opener.open(request)

"""
request = urllib.request.Request('https://blog.csdn.net/ccat/article/details/7486181', data=vs_key)

request.add_header('Content-Type', 'application/json')
request.get_method = lambda: 'PUT'
response = urllib.request.urlopen(request)
"""

hostname = "10.12.32.61"
port = "22"
username = "root"
password = "BigIP123"
command = ["cat bigip.conf","cat profile_base.conf","cat bigip_base.conf"]
test(hostname,port,username,password,command)

