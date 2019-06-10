import json
import requests
import sys
import boto3

cloudwatch = boto3.client('cloudwatch')
rabbitmq_url = ''   #URL to specific RabbitMQ queue to monitor

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
try:
    rabbit_result = requests.get(rabbitmq_url, auth=('', ''), timeout=30)    #Username/Password for RabbitMQ instance
except Exception as e:
    f = open("search_monitor_log.txt", "a")
    f.write(str(e))
    f.write("\n")
    f.close()
    sys.exit(0)
queue_stats = json.loads(rabbit_result.text)
messages_ready = queue_stats['messages_ready']
post_metric("Monitoring", "RabbitMQ Search Queue Length", 'Count', messages_ready)