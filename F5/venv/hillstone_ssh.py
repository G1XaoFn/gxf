#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import paramiko
import time
import json
import requests

try:
    # python2
    reload(sys)
    sys.setdefaultencoding("utf-8")
except:
    # python3
    import importlib

    importlib.reload(sys)


def pa_invoke_shell(ip, port, username, password, commands):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, port, username, password)
    channel = ssh.invoke_shell(width=1000)
    result_list = []
    for cmd in commands:
        channel.send(cmd)
        time.sleep(0.1)
        result = channel.recv(65535)
        while True:
            channel.send(" ")
            time.sleep(0.1)
            results = channel.recv(65535)
            if results == b' ':
                break
            result += results
        result_list.append(result.decode('utf-8'))

    channel.close()
    ssh.close()
    return result_list


if __name__ == '__main__':
    host_ip = "10.12.32.49"
    username = "hillstone"
    password = "hillstone"
    input_commands = ['terminal length 0\n',
                      'show config\n',
                      'show ip route\n',
                      'show service predefined\n',
                      'show servgroup predefined\n',
                      'show application predefined\n',
                      'show application-group predefined\n'
                      ]
    shell_output = pa_invoke_shell(ip=host_ip, port=22, username=username, password=password, commands=input_commands)

    requests.post('http://dev.paas.bk.com:8000/v1.0/common-device-config/gathering-result/',
                  data={'host_ip': host_ip,
                        'gathering_method': 'ssh',
                        'input_commands': json.dumps(input_commands),
                        'output_content': json.dumps(shell_output)})
