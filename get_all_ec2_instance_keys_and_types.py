from __future__ import print_function
import boto3
import sys
import paramiko
import subprocess
import time

#TODO consider combining powershell commands into one


ec2_resource = boto3.resource('ec2')
ssm_client = boto3.client('ssm')

instance_data = {}
linux_usernames = ["root", "admin", "ec2-user", "ubuntu"]

#powershell to get count, both important and optional:
update_powershell_script = ["$Computername = $env:COMPUTERNAME",
                            "$updatesession =  [activator]::CreateInstance([type]::GetTypeFromProgID(\"Microsoft.Update.Session\",$Computername))",
                            "$UpdateSearcher = $updatesession.CreateUpdateSearcher()",
                            "$searchresult = $updatesearcher.Search(\"IsInstalled=0\")",
                            "$searchresult.Updates | Select KBArticleIds | foreach {$_.KbArticleids}"]

uptime_version_powershell_script = [
    '$timeSpan = (Get-Date) - [Management.managementDateTimeConverter]::ToDateTime((Get-WmiObject Win32_OperatingSystem).LastBootUpTime)',
    '"{0:00} d {1:00} h {2:00} m {3:00} s" -f $timeSpan.Days, $timeSpan.Hours, $timeSpan.Minutes, $timeSpan.Seconds',
    '(Get-WmiObject Win32_OperatingSystem).Version'
]

def main():
    csv_data = "InstanceId,IP,Hostname,Uptime,Version,OS,Update\n"
    #Get all of the ec2 instances
    instances = ec2_resource.instances.filter()

    #Get all of the instances with SSM configured, and just grab the instance ids from that list
    #TODO there's 43 current instances, need to figure out how to get all of them if we get past 50
    ssm_instances = ssm_client.describe_instance_information(MaxResults=50)
    ssm_instance_ids = list(instance["InstanceId"] for instance in ssm_instances["InstanceInformationList"])


    #Iterate through the list and build a more simple object, and adding whether or not SSM is enabled based on the previous list
    for instance in instances:
        product_family_tag = next((tag["Value"] for tag in instance.tags if tag["Key"] == "ProductFamily"), None)
        database_tag = next((tag["Value"] for tag in instance.tags if tag["Key"] == "ProductModule"), None)
        if (str(instance.id) in ssm_instance_ids):
            tempObject = {"Key": instance.key_name, "Platform": instance.platform, "IP": instance.private_ip_address, "SSMEnabled": True}
        else:
            tempObject = {"Key": instance.key_name, "Platform": instance.platform, "IP": instance.private_ip_address, "SSMEnabled": False}
        instance_data[instance.id] = tempObject
        

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for instance_id in instance_data:
        update_count = 0
        if (str(instance_data[instance_id]["Platform"]) == "None" and str(instance_data[instance_id]["Key"]) != "None"): #Linux instances with a key configured
            print("Getting " + instance_id + "'s data...")
            keyfile_string = str(instance_data[instance_id]["Key"]) + ".pem"
            for username in linux_usernames:
                try:
                    ssh.connect(
                        instance_data[instance_id]["IP"], 
                        username=username, 
                        key_filename=keyfile_string, 
                        timeout=30)
                except:
                    continue
                ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("cat /proc/version", timeout=30)
                result = ssh_stdout.readlines()
                #If we guessed the username wrong, try the next one
                if (str(result[0]).find("Please login as the") != -1):
                    continue
                
                kernel_version = result[0].split()[2]

                #check the version string that was returned for red hat or ubuntu
                if (str(result[0]).find("Red Hat") != -1):
                    #first, get the hostname
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("hostname", timeout=30)
                    hostname = ssh_stdout.readlines()

                    #then get the uptime
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("uptime | sed 's/.*up \([^,]*\), .*/\\1/'", timeout=30)
                    uptime = ssh_stdout.readlines()

                    #then get the OS version, distro specific
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("awk -F= '$1--\"PRETTY_NAME\" {print $2;}' /etc/os-release", timeout=30)
                    os_version = ssh_stdout.readlines()
                    os_version = os_version[0].replace('"', '').strip() + " " + os_version[1].replace('"', '').strip()

                    #then get the updates
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("yum check-update", timeout=30)
                    result = ssh_stdout.readlines()
                    update_count = len(result) - 2 #the first two elements are the loaded plugins followed by a newline
                    for update in result:
                        if (str(update).find("Loaded") == -1 and str(update).find("Loading") == -1 and str(update) != "\n" and str(update)[:2] != " *" and str(update).find("packages excluded") == -1 and str(update).find("Determining fastest mirrors") == -1):
                            csv_data += instance_id + "," + instance_data[instance_id]["IP"] + "," + hostname[0].strip() + "," + uptime[0].strip() + "," + kernel_version + "," + os_version + "," + update #newline is included in the result
                            update_count += 1

                elif (str(result[0]).find("Ubuntu") != -1):
                    #first, get the hostname
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("hostname", timeout=30)
                    hostname = ssh_stdout.readlines()

                    #then get the uptime
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("uptime | sed 's/.*up \([^,]*\), .*/\\1/'", timeout=30)
                    uptime = ssh_stdout.readlines()

                    #then get the OS version, distro specific
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("awk -F= '$1--\"PRETTY_NAME\" {print $2;}' /etc/os-release", timeout=30)
                    os_version = ssh_stdout.readlines()
                    os_version = os_version[0].replace('"', '').strip() + " " + os_version[1].replace('"', '').strip()

                    #then get the actual updates
                    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("apt list --upgradeable", timeout=30)
                    result = ssh_stdout.readlines()
                    update_count = len(result)
                    for update in result:
                        if (str(update).find("Loaded") == -1 and str(update).find("Listing...") == -1):
                            csv_data += instance_id + "," + instance_data[instance_id]["IP"] + "," + hostname[0].strip() + "," + uptime[0].strip() + "," + kernel_version + "," + os_version + "," + update
                            update_count += 1


        if (str(instance_data[instance_id]["Platform"]) == "windows" and instance_data[instance_id]["SSMEnabled"]):   #if it's windows and SSM is enabled because surprisingly that's the easiest
            print("Getting " + instance_id + "'s data...")
            #first, get the hostname
            hostname = run_powershell_script(["hostname"], instance_id)

            #then get the uptime and the OS version in one go
            uptime_version = run_powershell_script(uptime_version_powershell_script, instance_id)

            #then get the actual updates
            command_result = run_powershell_script(update_powershell_script, instance_id)
            for kb in command_result.split():
                csv_data += instance_id + "," + instance_data[instance_id]["IP"] + "," + hostname.strip() + "," + uptime_version.splitlines()[0] + "," + uptime_version.splitlines()[1] + ",Windows" +  ",KB" + kb + "\n"
                update_count += 1
                
    file = open('updates.csv', "w")
    print(csv_data, file=file)



def run_powershell_script(function_to_run, instance_id):
    response = ssm_client.send_command(
        InstanceIds = [instance_id],
        DocumentName = 'AWS-RunPowerShellScript',
        Parameters = {
            'commands': function_to_run
        }
    )
    command_status = response["Command"]["Status"]
    command_id = response["Command"]["CommandId"]
    while(command_status == "Pending" or command_status == "InProgress"):
        time.sleep(3) #wait a moment
        command_invocation = ssm_client.get_command_invocation(CommandId = command_id, InstanceId = instance_id)
        command_status = command_invocation["Status"]
    if (command_status == "Success"):
        command_invocation = ssm_client.get_command_invocation(CommandId = command_id, InstanceId = instance_id)
        command_result = command_invocation["StandardOutputContent"]
    return str(command_result)
    #TODO need to handle error in result


if __name__ == "__main__":
    main()
