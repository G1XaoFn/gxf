# -*- coding: utf-8 -*-
# @Time : 2020/8/7 12:51
# @Author : Alva
# @File : 脚本解析v-2.py

import re
import sys
import telnetlib
import threading
import time
import logging
import json

from io import StringIO
from time import strftime, localtime

try:
    # python3
    from io import StringIO
except:
    # python2
    from StringIO import StringIO

try:
    reload(sys)
    sys.setdefaultencoding('utf8')
except:
    import importlib

    importlib.reload(sys)

host_ip = '10.12.32.36'
username = 'abt'
password = 'Abt@123.com'
content = None
current_time = strftime("%Y%m%d  %H %M %S", localtime())
filename = f'parse_data{current_time}.log'


def get_logger(filename=filename):
    """
    获取保存日志logger
    :param filename: 文件名，包含全绝对路径
    :return:
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(level=logging.INFO)

    handler = logging.FileHandler(filename, encoding='utf-8')
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = get_logger()


class TelnetClient(object):

    def __init__(self, host_ip, username, password):
        self.host_ip = host_ip
        self.username = username
        self.password = password
        self.tn = telnetlib.Telnet()

    # 此函数实现telnet登录主机
    def login_host(self):
        try:
            self.tn.open(self.host_ip, port=23)
        except:
            text = '{} 网络连接失败'.format(self.host_ip)
            logger.info(text)
            return False
        # 等待login出现后输入用户名，最多等待10秒
        self.tn.read_until(b'Username:', timeout=10)
        self.tn.write(self.username.encode('ascii') + b'\n')
        # 等待Password出现后输入用户名，最多等待10秒
        self.tn.read_until(b'Password:', timeout=10)
        self.tn.write(self.password.encode('ascii') + b'\n')
        # 延时两秒再收取返回结果，给服务端足够响应时间
        time.sleep(2)
        self.tn.write('terminal length 0'.encode('ascii') + b'\n')
        # 获取登录结果
        # read_very_eager()获取到的是的是上次获取之后本次获取之前的所有输出
        command_result = self.tn.read_very_eager().decode('ascii')
        if 'error' not in command_result:
            logger.info('%s connected ssuccess !' % self.host_ip)
            return True
        else:
            logger.info('%s failed to login，username or password error !' % self.host_ip)
            return False

    # 此函数实现执行传过来的命令，并输出其执行结果
    def execute_some_command(self, command):
        # 执行命令
        self.tn.write(command.encode('ascii') + b'\n')
        time.sleep(5)
        # 获取命令结果
        command_result = self.tn.read_very_eager().decode('ascii')
        # logger.info('%s 防火墙配置文件' % command_result)
        return command_result

    # 退出telnet
    def logout_host(self):
        self.tn.write(b"exit\n")
        logger.info('本次操作结束，连接断开\n')


# 全局变量存储类
class GlobalClass(object):
    _instance_lock = threading.Lock()
    format_data = []
    format_data_dict = {}
    hit_class = None
    line_data = None
    line_number = 0
    Starting_line_number = 0
    version = None
    hostname = None

    # 单例模式
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, '_instance'):
            with GlobalClass._instance_lock:
                if not hasattr(cls, '_instance'):
                    GlobalClass._instance = super(GlobalClass, cls).__new__(cls)
        return GlobalClass._instance


# 解析块基类
class LogicBlock(object):
    """
    正则解析块基类，所有处理要处理的解析块均需继承该类，并实现相应的方法
    """
    global_class = GlobalClass()

    def __int__(self):
        pass

    @classmethod
    def checkout_pattern(cls):
        return False

    @classmethod
    def perform_process(cls):
        pass


# show ip interface brief命令解析
class ShowIpInterfaceBrief(LogicBlock):
    @classmethod
    def checkout_pattern(cls):
        sre = re.match('Interface\s+IP-Address\s+OK\?\s+Method Status\s+Protocol', cls.global_class.line_data.strip())
        if sre:
            return __class__.__name__

    @classmethod
    def perform_process(cls):
        sre = re.match('(?P<interface>[\w/]+)\s+(?P<ip_address>[a-z]+|[0-9\.]{7,15})\s+',
                       cls.global_class.line_data.strip())
        if sre:
            dic = {
                'interface_name': sre.group('interface'),
                'ip_address': sre.group('ip_address'),
                'line': f'{cls.global_class.line_number}',
            }
            if dic['ip_address'] == 'unassigned':
                dic['ip_address'] = None
            if cls.global_class.format_data_dict.get('interface'):
                cls.global_class.format_data_dict['interface'].append(dic)
            else:
                cls.global_class.format_data_dict['interface'] = [dic]
            logger.info(f'{cls.global_class.line_number}行解析成功')
            return True


# show running-config interface命令解析
class ShowRunningConfig(LogicBlock):
    state = 0
    block_data = ''

    @classmethod
    def checkout_pattern(cls):
        # 检验是否是当前类解析道行
        sre = re.search('(?=\\b)^interface +([\w\-/\|]+)$', cls.global_class.line_data)
        if sre:
            # 设置首行行号及重置block_data
            cls.global_class.Starting_line_number = cls.global_class.line_number
            cls.block_data = cls.global_class.line_data
            return __class__.__name__

    @classmethod
    def perform_process(cls):
        # 如果当前行数据是首行, 将已经保存好的block_data进行集体解析并重置block_data
        sre = re.search('(?=\\b)^interface +(?P<interface>([\w\-/\|]+))$', cls.global_class.line_data)
        if sre:
            # 准备解析block_data
            sre_interface = re.search('(?=\\b)^interface +(?P<interface>([\w\-/\|]+))(?=\\n)', cls.block_data)
            sre_acl_name = re.findall('ip +access-group +(?P<acl_name>.*)\n', cls.block_data)
            sre_pbr_name = re.search('ip +policy route-map +(?P<pbr_name>.*)\n', cls.block_data)
            if sre_interface:
                access_group_list = []
                for i in sre_acl_name:
                    i = i.split(' ')
                    access_group = {'acl_name': i[0], 'direction': i[-1]}
                    access_group_list.append(access_group)
                dic = {
                    'interface': sre_interface.group('interface'),
                    'access-group': access_group_list or None,
                    'pbr_name': None if not sre_pbr_name else sre_pbr_name.group(1),
                    'line': f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number - 1}',
                }
                if cls.global_class.format_data_dict.get('show_run_config'):
                    cls.global_class.format_data_dict['show_run_config'].append(dic)
                else:
                    cls.global_class.format_data_dict['show_run_config'] = [dic]
                logger.info(f'{cls.global_class.line_number}行推送了块数据到全局')
                cls.global_class.Starting_line_number = cls.global_class.line_number
                cls.block_data = cls.global_class.line_data
                return True
            else:
                logger.warning(
                    f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number}行数据块不匹配, 该数据块未保存')
                cls.block_data = ''
                cls.global_class.Starting_line_number = cls.global_class.line_number
                return
        if not cls.block_data:
            cls.global_class.Starting_line_number = cls.global_class.line_number
        cls.block_data += cls.global_class.line_data
        logger.info(f'{cls.global_class.line_number}行添加入数据块')
        return True


# show access-lists命令解析
class ShowAccessLists(LogicBlock):
    ip_access_list = None

    @classmethod
    def checkout_pattern(cls):
        sre = re.search('IP(v4|v6)? +access[ \-]+list +(\w+ +)*(?P<ip_access_list>[&/\w-]+)(?!P[&/\w-]+)',
                        cls.global_class.line_data,
                        re.IGNORECASE)
        if sre:
            cls.ip_access_list = sre.group('ip_access_list')
            return __class__.__name__
        return False

    @classmethod
    def perform_process(cls):
        sre = re.search(
            'IP(v4|v6)? +access[ \-]+list +(\w+ +)*(?P<ip_access_list>[&/\w-]+)(?!P[&/\w-]+)| *(?P<_sequence>\d+)? *(?P<action>permit|deny) +(?P<protocol>([a-z0-9]+) +)?(?P<source>(([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2}| ([0-9]{1,3}\.){3}[0-9]{1,3})|host ([0-9]{1,3}\.){3}[0-9]{1,3}|any|([0-9]{1,3}\.){3}[0-9]{1,3})|addrgroup(?P<source_addrgroup>((?! ([0-9]{1,3}\.){3}[0-9]{1,3}| any| addrgroup| portgroup| host| sequence)[ \w-])*))(?P<source_port>((?! ([0-9]{1,3}\.){3}[0-9]{1,3}| any| addrgroup| portgroup| host| sequence)[ \w-])*)( portgroup (?P<source_portgroup>[\w-]+))?( (?P<dest>(([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2}| ([0-9]{1,3}\.){3}[0-9]{1,3})|host ([0-9]{1,3}\.){3}[0-9]{1,3}|any|([0-9]{1,3}\.){3}[0-9]{1,3})|addrgroup(?P<dest_addrgroup>((?! ([0-9]{1,3}\.){3}[0-9]{1,3}| any| addrgroup| portgroup| host| sequence)[ \w-])*))(?P<dest_port>((?! ([0-9]{1,3}\.){3}[0-9]{1,3}| any| addrgroup| portgroup| host| sequence)[ \w-])*)( portgroup (?P<dest_portgroup>[\w-]+))?)?( *sequence +(?P<sequence>\d+))?',
            cls.global_class.line_data.replace(', wildcard bits', ''), re.IGNORECASE)
        if sre:
            if sre.group('ip_access_list'):
                cls.ip_access_list = sre.group('ip_access_list')
            else:
                dic = {
                    'acl_name': cls.ip_access_list,
                    'action': sre.group('action'),
                    'line': f'{cls.global_class.line_number}'
                }
                if sre.group('protocol'):
                    dic['protocol'] = sre.group('protocol').strip()

                if sre.group('source_addrgroup'):
                    dic['source_addrgroup'] = sre.group('source_addrgroup').strip()
                else:
                    dic['source'] = sre.group('source')

                if sre.group('source_portgroup'):
                    dic['source_portgroup'] = sre.group('source_portgroup').strip()
                elif sre.group('source_port'):
                    dic['source'] = sre.group('source').strip()
                    dic['source_port'] = sre.group('source_port').strip()

                if sre.group('dest_addrgroup'):
                    dic['dest_addrgroup'] = sre.group('dest_addrgroup').strip()
                else:
                    dic['dest'] = sre.group('dest')

                if sre.group('dest_portgroup'):
                    dic['dest_portgroup'] = sre.group('dest_portgroup').strip()
                elif sre.group('dest_port'):
                    dic['dest'] = sre.group('dest').strip()
                    dic['dest_port'] = sre.group('dest_port').strip()

                if sre.group('sequence'):
                    dic['sequence'] = sre.group('sequence').strip()

                if sre.group('_sequence'):
                    dic['sequence'] = sre.group('_sequence')

                if cls.global_class.format_data_dict.get('sw_acl_rule'):
                    cls.global_class.format_data_dict['sw_acl_rule'].append(dic)
                else:
                    cls.global_class.format_data_dict['sw_acl_rule'] = [dic]
            return True


class ShowRouteMap(LogicBlock):
    block_data = ''

    @classmethod
    def checkout_pattern(cls):
        sre = re.search('route-map +[&/\w-]+,? +(deny|permit),?', cls.global_class.line_data, re.IGNORECASE)
        if sre:
            cls.block_data = cls.global_class.line_data
            cls.global_class.Starting_line_number = cls.global_class.line_number
            return __class__.__name__

    @classmethod
    def perform_process(cls):
        if re.search('route-map|exit', cls.global_class.line_data.strip()):
            sre = re.search(
                'route-map +(?P<pbr_name>[/\w\-&]+),? +(?P<allow_or_not>deny|permit)[\s\S]+ip +address +(\(access-lists\): )?(?P<acl_name>[\w\-& ]+)\\n\s*([\s\S]*ip +next[ -]?hop +(?P<nexthop>[0-9\./]{7,18})\\b)?',
                cls.block_data, re.IGNORECASE
            )
            if sre:
                dic = {
                    'action': sre.group('allow_or_not'),
                    'acl_name': sre.group('acl_name').split(' '),
                    'nexthop': sre.group('nexthop'),
                    'pbr_name': sre.group('pbr_name'),
                    'line': f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number - 2}'
                }
                if cls.global_class.format_data_dict.get('show_route_map'):
                    cls.global_class.format_data_dict['show_route_map'].append(dic)
                else:
                    cls.global_class.format_data_dict['show_route_map'] = [dic]
                logger.info(f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number - 2}数据块成功推送')
            else:
                logger.warning(
                    f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number - 2}数据块不匹配, 数据未保存')
            # 重置数据块信息
            cls.block_data = cls.global_class.line_data
            cls.global_class.Starting_line_number = cls.global_class.line_number
            return True
        else:
            cls.block_data += cls.global_class.line_data
            logger.info(f'{cls.global_class.line_number}行数据提交到块数据')
            return True


# show forwarding ipv4 route
class ShowForwardingIpv4Route(LogicBlock):
    @classmethod
    def checkout_pattern(cls):
        sre = re.search('Prefix[ \|]+Next[ -]+Hop[ \|]+Interface\\b', cls.global_class.line_data, re.IGNORECASE)
        if sre:
            return __class__.__name__

    @classmethod
    def perform_process(cls):
        sre = re.search(
            '(?P<prefix>[0-9\./]{9,18})\s+(?P<nexthop>[0-9\./]{7,18}|Drop|Receive|attached)(\s+(?P<interface>[\w\-/]+))?',
            cls.global_class.line_data, re.IGNORECASE)
        if sre:
            dic = {
                'prefix': sre.group('prefix'),
                'nexthop': sre.group('nexthop'),
                'interface': sre.group('interface'),
                'line': f'{cls.global_class.line_number}',
            }
            if cls.global_class.format_data_dict.get('ip_routes'):
                cls.global_class.format_data_dict['ip_routes'].append(dic)
            else:
                cls.global_class.format_data_dict['ip_routes'] = [dic]
            return True


class ShowRun(LogicBlock):
    group_type = None
    group_name = None
    block_data = ''
    state = 0

    @classmethod
    def checkout_pattern(cls):
        sre = re.search('object-group +(?P<group_type>.+?) +(?P<group_name>[\w\-]+)$',
                        cls.global_class.line_data)
        if sre:
            cls.group_type = sre.group('group_type')
            cls.group_name = sre.group('group_name')
            cls.block_data = ''
            cls.state = 1
            cls.global_class.Starting_line_number = cls.global_class.line_number
            return __class__.__name__

    @classmethod
    def perform_process(cls):
        sre = re.search('object-group +(?P<group_type>.+?) +(?P<group_name>[\w\-]+)$',
                        cls.global_class.line_data)
        sre2 = re.search('^!$|(?=\\n)^\\n|^exit', cls.global_class.line_data)
        if sre:
            cls.group_type = sre.group('group_type')
            if cls.group_type == 'ip address':
                cls.group_type = 'network'
            if cls.group_type == 'ip port':
                cls.group_type = 'service'
            cls.group_name = sre.group('group_name')
            if cls.block_data:
                group_values = re.split('\\n', cls.block_data)
                dic = {
                    'group_type': cls.group_type,
                    'address_name': cls.group_name,
                    'servgroup_name': cls.group_name,
                    'member': '!'.join([i.strip() for i in group_values]).strip().strip('!').split('!'),
                    'line': f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number - 1}',
                    'version': cls.global_class.version,
                    'hostname': cls.global_class.hostname,
                }
                for i in range(len(dic['member'])):
                    dic['member'][i] = re.sub('^\d+ +', '', dic['member'][i])

                if dic['group_type'] == 'network':
                    if cls.global_class.format_data_dict.get('address'):
                        cls.global_class.format_data_dict['address'].append(dic)
                    else:
                        cls.global_class.format_data_dict['address'] = [dic]
                else:
                    dic['service'] = dic['member']
                    dic.pop('member')
                    if cls.global_class.format_data_dict.get('servgroup'):
                        cls.global_class.format_data_dict['servgroup'].append(dic)
                    else:
                        cls.global_class.format_data_dict['servgroup'] = [dic]
                logger.info(f'{cls.global_class.line_number}推送数据到全局')
            cls.block_data = ''
            cls.state = 1
            cls.global_class.Starting_line_number = cls.global_class.line_number
            logger.info(f'{cls.global_class.line_number}添加数据到块')
            return True
        elif sre2:
            if cls.state:
                group_values = re.split('\\n', cls.block_data)
                dic = {
                    'group_type': cls.group_type,
                    'address_name': cls.group_name,
                    'servgroup_name': cls.group_name,
                    'member': '!'.join([i.strip() for i in group_values]).strip().strip('!').split('!'),
                    'line': f'{cls.global_class.Starting_line_number}~{cls.global_class.line_number - 1}',
                    'version': cls.global_class.version,
                    'hostname': cls.global_class.hostname,
                }
                for i in range(len(dic['member'])):
                    dic['member'][i] = re.sub('^\d+ +', '', dic['member'][i])

                if dic['group_type'] == 'network':
                    if cls.global_class.format_data_dict.get('address'):
                        cls.global_class.format_data_dict['address'].append(dic)
                    else:
                        cls.global_class.format_data_dict['address'] = [dic]
                else:
                    dic['service'] = dic['member']
                    dic.pop('member')
                    if cls.global_class.format_data_dict.get('servgroup'):
                        cls.global_class.format_data_dict['servgroup'].append(dic)
                    else:
                        cls.global_class.format_data_dict['servgroup'] = [dic]
                cls.block_data = ''
                cls.state = 0
                logger.info(f'{cls.global_class.line_number}推送数据到全局')
                return True
        elif cls.state:
            cls.block_data += cls.global_class.line_data
            logger.info(f'{cls.global_class.line_number}添加数据到块')
            return True


def hit_logic_block(global_class):
    """
    获取所有解析块子类，并循环判断是否是该子类的处理内容，并执行相应处理
    :param global_class:
    :return: None
    """
    subclasses = LogicBlock.__subclasses__()
    for subclass in subclasses:
        logger.info(f'{global_class.line_number}行正在与{subclass}进行匹配')
        hit_class = getattr(subclass, 'checkout_pattern')()
        if hit_class:
            logger.info(f'行数{global_class.line_number}, 命中类{hit_class},\n命中行数据:\n{global_class.line_data}')
            global_class.hit_class = subclass
            break


# 确定version及hostname
def get_version_or_hostname(global_class):
    sre = re.match('version +(?P<version>[0-9\.]+)|hostname +(?P<hostname>[\w\-]+)', global_class.line_data)
    if sre:
        global_class.version = global_class.version or sre.group('version')
        global_class.hostname = global_class.hostname or sre.group('hostname')


# 山石防火墙配置文本解析主函数
def resolve(_content):
    _content = StringIO(_content)
    global_class = GlobalClass()
    global_class.line_number = 1
    for line_data in _content:
        global_class.line_data = line_data

        # 确定version及hostname
        if not global_class.version or not global_class.hostname:
            get_version_or_hostname(global_class)

        # 现在的全局变量类就是当前行数据 + 行号
        if not global_class.hit_class:
            hit_logic_block(global_class)
        else:
            result = getattr(global_class.hit_class, 'perform_process')()
            if not result:
                logger.warning(
                    f'不匹配; 行号:{global_class.line_number}; 使用解析类:{global_class.hit_class};\n不匹配数据:\n{global_class.line_data}')
            else:
                logger.info(f'解析结果:{result}; 行号:{global_class.line_number}; 使用解析类:{global_class.hit_class}')
        global_class.line_number += 1
    global_class.line_data = 'exit'
    if global_class.hit_class:
        getattr(global_class.hit_class, 'perform_process')()
        logger.info(f'{global_class.line_number}行，正确退出')
    else:
        logger.warning(f'警告:{global_class.line_number}行，无数据退出')
    return global_class.hit_class


# 获取最终格式化的结果
def get_resolve_data():
    # return json.dumps({hit_class.__name__: GlobalClass.format_data}, indent=4, sort_keys=True, ensure_ascii=False)
    return json.dumps(GlobalClass.format_data_dict, indent=4, sort_keys=True, ensure_ascii=False)


if __name__ == '__main__':
    # telnet_client = TelnetClient(host_ip, username, password)
    # # 如果登录结果返加True，则执行命令，然后退出
    # if telnet_client.login_host():
    #     # content就是最终从远程主机拿到的返回结果
    #     content = telnet_client.execute_some_command('show ip interface brief')
    # telnet_client.logout_host()

    # 从文本文件读取
    with open('交换机33', 'r', encoding='utf-8') as f:
        content = f.read()

    # 拿到字符串正式开始解析
    logger.info('解析开始')
    hit_class = resolve(content)
    format_data = get_resolve_data()
    logger.info('解析完成')
    print(format_data)
