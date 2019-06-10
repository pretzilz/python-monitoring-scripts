from __future__ import print_function
import boto3
import sys


csv_data = "InstanceName,PublicIP,Protocol,PortRange,IP,Description\n"
#Returns a list of objects: Protocol - PortRange - IP - Description
#list_of_visited_groups contains a list of all previously visited security groups if we recurse, to detect cycles.
def GetSecurityGroupRules(security_group_object, list_of_visited_groups):
    security_group_rules = []

    ingress_rules = security_group_object.ip_permissions
    for ingress_rule in ingress_rules:
        temp_object = {}
        #If this rule is either TCP or UDP specifically, it will have a port range
        if ingress_rule["IpProtocol"] != '-1':
            ip_protocol = ingress_rule["IpProtocol"]
            port_range = str(ingress_rule["FromPort"]) + " - "  + str(ingress_rule["ToPort"])
            for ip in ingress_rule["IpRanges"]:
                if 'Description' in ip.keys():
                    temp_object = {"Protocol": ip_protocol, "PortRange": port_range, "IP": ip["CidrIp"], "Description": ip["Description"]}
                else:
                     temp_object = {"Protocol": ip_protocol, "PortRange": port_range, "IP": ip["CidrIp"], "Description": ""}
                security_group_rules.append(temp_object) 
        #All protocols - all traffic - no port range
        else:
            ip_protocol = ingress_rule["IpProtocol"]
            port_range = "All Traffic"
            for ip in ingress_rule["IpRanges"]:
                if 'Description' in ip.keys():
                    temp_object = {"Protocol": ip_protocol, "PortRange": port_range, "IP": ip["CidrIp"], "Description": ip["Description"]}
                else:
                     temp_object = {"Protocol": ip_protocol, "PortRange": port_range, "IP": ip["CidrIp"], "Description": ""}
                security_group_rules.append(temp_object)
        
        #If there are any embedded security groups, get the rules for those as well and append them to the list
        if ingress_rule["UserIdGroupPairs"] != []:
                for embedded_group in ingress_rule["UserIdGroupPairs"]:
                    security_group_id = embedded_group["GroupId"]
                    if security_group_id not in list_of_visited_groups:
                        #If we haven't visited this group, mark that we have, then visit it
                        list_of_visited_groups.append(security_group_id)
                        embedded_group_object = ec2_resource.SecurityGroup(security_group_id)
                        embedded_rules = GetSecurityGroupRules(embedded_group_object, list_of_visited_groups)
                        for rule in embedded_rules:
                            security_group_rules.append(rule)
        
        #Finally, return the object
        return security_group_rules




ec2_resource = boto3.resource('ec2')

instances = ec2_resource.instances.all()

instances_with_public_ips = list(instance for instance in instances if instance.public_ip_address != None)

for instance in instances_with_public_ips:
    instance_name = next(tag["Value"] for tag in instance.tags if tag["Key"] == "Name")
    instance_ingress_rules = []
    for security_group in instance.security_groups:
        security_group_object = ec2_resource.SecurityGroup(security_group["GroupId"])
        rules = GetSecurityGroupRules(security_group_object, [])
        instance_ingress_rules.extend(rules)

    for rule in instance_ingress_rules:
        csv_data += str(instance_name) + "," + str(instance.public_ip_address) + "," + rule["Protocol"] + "," + rule["PortRange"] + "," + rule["IP"] + "," + rule["Description"] + "\n"
    
file = open('publicly_accessible_instances.csv', "w")
print(csv_data, file=file)




