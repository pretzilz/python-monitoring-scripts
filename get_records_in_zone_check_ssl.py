import requests
import ssl, socket
import boto3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.ssl_ import create_urllib3_context
from urllib.parse import urlparse



def main():
    csv_data = "Record,CertSubject,Issuer,ExpirationDate\n"
    zones_to_check = [""] #Route53 zone name
    zone_ids = []
    r53_client = boto3.client("route53")
    for zone in zones_to_check:
        zone_metadata = r53_client.list_hosted_zones_by_name(DNSName=zone, MaxItems="1")
        zone_id = zone_metadata["HostedZones"][0]["Id"]
        record_sets = r53_client.list_resource_record_sets(HostedZoneId=zone_id)
        record_set_list = record_sets["ResourceRecordSets"]
        while record_sets["IsTruncated"]:
            next_record = record_sets["NextRecordName"]
            next_record_type = record_sets["NextRecordType"]
            record_sets = r53_client.list_resource_record_sets(HostedZoneId=zone_id, StartRecordName=next_record, StartRecordType= next_record_type)
            record_set_list.extend(record_sets["ResourceRecordSets"])
        for record in record_set_list:
           csv_data += test_record(record["Name"])
    file = open('route_53_cert_information.csv', "w")
    print(csv_data, file=file)


def test_record(record_name):
    record_name = record_name[:-1]
    try:
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(socket.socket(), server_hostname=record_name)
        s.settimeout(5)
        s.connect((record_name, 443))
        cert = s.getpeercert()
        subject = dict(x[0] for x in cert['subject'])
        issued_to = subject['commonName']
        issuer = dict(x[0] for x in cert['issuer'])
        issued_by = issuer['commonName']
        ssl_expiration = cert['notAfter']
        print(record_name + "\t" + issued_to + "\t" + issued_by + "\t" + ssl_expiration)
        return record_name + "," + issued_to + "," + issued_by + "," + ssl_expiration + "\n"
    except Exception as e:
        print("Getting the certificate for " + record_name + " failed! Exception: " + str(e)) 
        return record_name + "," + "Failed/NoCert" + "," + str(e) + "\n"
    
if __name__ == "__main__":
    main()
