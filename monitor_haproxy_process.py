import boto3
import json
import requests
import sys
import paramiko

ha_proxy_nodes = [
    {'AG': '', 'IPs': [""]}  #Availability group name/SQL Name, IP For HAProxy Nodes
]

namespace="HAProxy"
username="ec2-user"
keyfile="" #Keyfile for access to HAProxy instances


# Create CloudWatch client
cloudwatch = boto3.client('cloudwatch')

def post_metric(namespace,name,unit,value):
    cloudwatch.put_metric_data(
        MetricData=[
            {
                'MetricName': name,
                'Unit': unit,
                'Value': value
            },
        ],
        Namespace=namespace
    )


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

for group in ha_proxy_nodes:
    AG = group['AG']
    IPs = group['IPs']
    group_status = 0
    for ip in IPs:
        try:
            ssh.connect(ip, username=username, key_filename=keyfile, timeout=30, auth_timeout=30)
        except paramiko.SSHException:
            continue
        ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("sudo service haproxy status", timeout=10)
        result = ssh_stdout.readlines()
        if(str(result[0]).find("is running...") > -1):
            group_status += 1
    cloudwatch.put_metric_data(
            MetricData=[
                {
                    'MetricName': 'HAProxy Service',
                    'Dimensions': [
                        {
                            'Name': 'AG',
                            'Value': AG + " - " + "/".join(IPs)
                        },
                    ],
                    'Unit': 'Count',
                    'Value': group_status
                },
            ],
            Namespace=namespace
        )
