import paramiko
import time
import collections
import retry
import re
import textfsm

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
    result = {}

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
        #第一行是命令本身，作为key
        key = strResult[0]
        #删去第一行命令本身，只留下结果
        del strResult[0]
        #将结果加入字典
        result[key] = strResult
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

def init_result(result):
    '''
    对结果字符串的预处理，去除不必要的空格和字符
    :param result: 结果字符串列表
    :return: 处理过的字符串列表
    '''
    def delNone(n):
        return n!=""
    resultList = []
    #删除空行
    result = list(filter(delNone,result))
    for str in result:
        #去除每行前后的空格
        str.strip()
        if str[0] == "#":
            str = ""
        #在“{”，“}”左右加空格，因为有些地方这两个符号和其他字符串没有隔开

        #用空格分隔所有字符，并写进同一个list
        resultList.extend(str.split(" "))
    #去除列表中所有空字符串
    # while "" in resultList:
    #     resultList.remove("")
    resultList = list(filter(delNone,resultList))
    #处理本身是字符串的项被意外分隔的问题
    for i in range(len(resultList)):
        if "\"" in resultList[i]:
            #判断一下这一个字符串是否为完整的，如果完整，就没必要再找字符串的结束“了
            tem = resultList[i]
            tem.replace("\"","",1)
            if "\"" in tem:
                continue
            for j in range(i+1, len(resultList)):
                #将resultList[j]加到i上，恢复带空格的字符串
                resultList[i] += " "
                resultList[i] += resultList[j]
                #如果找到了对应的结束双引号，退出循环
                if "\"" in resultList[j]:
                    #这边一定要先判断后标记，否则会被覆盖
                    resultList[j] = ""
                    break
                #标记已经加上去的字符串，方便后期删除
                resultList[j] = ""
    #去除标记的空字符串
    # while "" in resultList:
    #     resultList.remove("")
    resultList = list(filter(delNone, resultList))
    return resultList

def analysis_result(result):
    '''
    解析配置文件结构，递归
    :param result:
    :return: list
    '''
    #递归最终返回
    finalResult = []
    #如果list中没有继续嵌套的返回
    temlist = []
    #判断下一个最先出现的大括号是"{"还是"}",
    #如果是"}"则返回“}”前的内容，如果是“{”则说明还需要继续递归
    flag = False
    for str in result:
        if str == "{":
            break
        if str == "}":
            flag = True
    if flag:
        for str in result:
            if str == "}":
                break
            temlist.append(str)
        return temlist
    for i in range(len(result)):
        if result[i] == '{':
            temparam = []
            #将后面的整个字符串作为递归的参数
            for j in range(i+1, len(result)):
                temparam.append(result[j])
            #递归求解
            finalResult.append(analysis_result(temparam))
            #清理后面剩下的"}"，因为在每次递归已经处理，
            #但返回之后，result里已经处理过的数据还留着
            #使用空字符串对清理的内容标记
            count = 1
            Flag = False
            result[i] = ""
            for j in range(i+1, len(result)):
                if result[j] == "{":
                    count = count + 1
                elif result[j] == "}":
                    count = count - 1
                result[j] = ""
                if count == 0:
                    break
        #如果碰到了"}"，说明要返回
        elif result[i] == "}":
             return finalResult
        elif result[i] != "":
            finalResult.append(result[i])
    return finalResult

def split_conf(result):
    '''
    分割配置文件，将单独的一段配置提取出来
    :param result: 分析之后得到的列表
    :return: 一个包含着独立配置的列表
    '''
    finalResult = []
    temList = []
    for str in result:
        temList.append(str)
        #切片是以列表为分割标志的，因为观察发现每个独立配置都以“}”结尾
        if type(str).__name__ == "list":
            finalResult.append(list(temList))
            temList.clear()
    return finalResult

def search(list,seek):
    '''
    查找字段内容
    :param list: 要查找的列表
    :param seek: 要查找的字段
    :return: 如找到，返回字段的值，可能是字符串或列表，如未找到，返回None
    '''
    found = False
    for str in list:
        if found:
            return str
        if type(str).__name__ == "list":
            result = search(str,seek)
            if result != None:
                return result
        else:
            if str == seek:
                found = True

#一下这些都是配置文件中需要解析的结点
vs = {}
pools = {}
members = {}
snatpools = {}
persistences = {}
irules = {}
monitors = {}
routes = {}
selfs = {}
trunks = {}
vlans = {}
profiles = {}   #自定义的和系统定义的profile配置
profile = {}    #profile依赖关系
def get_profile(name,list):
    '''
    查找某个配置的继承关系，并添加到profile字典中
    :param name:配置名称
    :param list:配置list
    :return:None
    '''
    myProfile = search(list, "profile")
    myProfiles = search(list, "profiles")
    if (myProfile != None):
        profile[name] = myProfile
    elif (myProfiles != None):
        profile[name] = myProfiles
def get_name(list):
    '''
    将不同的配置类型放到不同的字典中，并获得名字以及继承关系
    :param list: spritedList
    :return: None
    '''
    for str in list:
        # virtual
        if str[0] == "ltm" and str[1] == "virtual":
            name = str[2]
            vs[name] = str
            get_profile(name, str)
        # pool
        elif str[0] == "ltm" and str[1] == "pool":
            name = str[2]
            pools[name] = str
            get_profile(name, str)
        # snatpool
        elif str[0] == "ltm" and str[1] == "snatpool":
            name = str[2]
            snatpools[name] = str
            get_profile(name, str)
        # profile
        elif str[0] == "ltm" and str[1] == "profile":
            name = str[3]
            profiles[name] = str
            get_profile(name, str)
        # persistence
        elif str[0] == "ltm" and str[1] == "persistence":
            name = str[3]
            persistences[name] = str
            get_profile(name, str)
        # irule
        elif str[0] == "ltm" and str[1] == "rule":
            name = str[2]
            irules[name] = str
            get_profile(name, str)
        # monitor
        elif str[0] == "ltm" and str[1] == "monitor":
            name = str[3]
            monitors[name] = str
            get_profile(name, str)
        # self
        elif str[0] == "net" and str[1] == "self":
            name = str[2]
            selfs[name] = str
            get_profile(name, str)
        # trunk
        elif str[0] == "net" and str[1] == "trunk":
            name = str[2]
            selfs[name] = str
            get_profile(name, str)
        # vlan
        elif str[0] == "net" and str[1] == "vlan":
            name = str[2]
            vlans[name] = str
            get_profile(name, str)

def get_profile_base(list):
    '''
    添加系统profile到profiles表
    :param list:
    :return:
    '''
    for str in list:
        if str[0] == "ltm" and str[1] == "profile":
            name = str[3]
            profiles[name] = str
            get_profile(name, str)

def get_profile_data(field,confName):
    '''
    寻找profile中的字段，递归查找
    :param field: 需要寻找的字段
    :param confName: 配置的名称
    :return:
    '''
    profileName = profile[confName]
    if profileName == None:
        return None
    if type(profileName).__name__ == "list":
        for str in profileName:
            if type(str).__name__ != "list":
                myProfile = profiles[profileName]
                ans = search(myProfile,field)
                if ans != None:
                    return ans
                else:
                    return get_profile_data(field, str)
    else:
        myProfile = profiles[profileName]
        ans = search(myProfile, field)
        if ans != None:
            return ans
        else:
            return get_profile_data(field, str)

results = [] # 最终的解析字段数据
def get_vs_field():
    '''
    获得vs的字段
    :return:
    '''
    vsList = vs.keys()
    for key in vsList:
        field = {}

        temName = re.findall(r".*/(.*)", key)[0]
        field["vs_name"] = temName

        temPath = re.findall(r"(.*/).*", key)[0]
        field["fullpath"] = temPath

        value = vs[key]

        temIpprotocol = search(value,"ip-protocol")
        if temIpprotocol == None:
            field["ipprotocol"] = get_profile_data("ip-protocol",key)
        else:
            field["ipprotocol"] = temIpprotocol

        temDestination = search(value,"destination")
        if temDestination == None:
            field["destination port"] = re.findall(r".*:(.*)",get_profile_data("destination",key))[0]
            field["destination ip"] = re.findall(r".*/(.*):.*",get_profile_data("destination",key))[0]
        else:
            field["destination port"] = re.findall(r".*:(.*)",temDestination)[0]
            field["destination ip"] = re.findall(r".*/(.*):.*", temDestination)[0]


        if temPath != None:
            field["partition"] = re.findall(r"/(.*)/",temPath)[0]
        else:
            field["partition"] = None

        temDestination = search(value,"description")
        if temDestination == None:
            field["description"] = get_profile_data("description",key)
        else:
            field["description"] = None

        temtext = search(value,"lws-width")
        if temtext == None:
            field["test"] = get_profile_data("lws-width",key)

        results.append(field)

@retry.retry(Exception, tries=3)
def resolver(hostname,port,username,password,command,n=0):
    '''
    解析文件
    :param hostname: 域名
    :param port: 端口
    :param username: 用户名
    :param password: 密码
    :param command: 指令列表
    :param n: 解析第n条指令的返回
    :return:
    '''
    #这个是要执行的指令，要对每一条指令加上回车
    execCommand = []
    for str in command:
        execCommand.append(str+"\n")
    ssh = ssh_connect(hostname,port,username,password)
    result = ssh_exec_command(ssh,execCommand)
    ssh_close(ssh)

    target = result.get(command[n])
    profileTarget = result.get("cat profile_base.conf")

    result = init_result(target)
    resultList = analysis_result(result)
    splitList = split_conf(resultList)

    profileResult = init_result(profileTarget)
    profileResultList = analysis_result(profileResult)
    profileSplitList = split_conf(profileResultList)

    get_profile_base(profileSplitList)
    get_name(splitList)

    # 删除profile中key==value的项，因为这说明配置文件没有继承其他对象
    temDelList = []  #这是个临时的列表，存着profile中要删除的key
    for tem in profile.keys():
        if profile[tem] == tem:
            temDelList.append(tem)
    for tem in temDelList:
        profile.pop(tem)

    get_vs_field()

    for i in profile.items():
        print(i)

    print(results)

    # return splitList
    return None

hostname = "10.12.32.61"
port = "22"
username = "root"
password = "BigIP123"
command = ["cat bigip.conf","cat profile_base.conf"]
time_begin = time.time()
result = resolver(hostname,port,username,password,command)
time_end = time.time()
print("用时:",time_end-time_begin)

#print(result)


