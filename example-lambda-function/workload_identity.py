#!/usr/bin/python
import json
import os
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
import boto3
import urllib
import requests

project_id = os.environ.get("PROJECT_ID")
project_number = os.environ.get("PROJECT_NUMBER")
pool_id = os.environ.get("POOL_ID")
provider_id = os.environ.get("PROVIDER_ID")
service_account = os.environ.get("SERVICE_ACCOUNT")

def create_token_aws(project_number: str, pool_id: str, provider_id: str) -> str:
    # Prepare a GetCallerIdentity request.
    request = AWSRequest(
        method="POST",
        url="https://sts.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15",
        headers={
            "Host": "sts.amazonaws.com",
            "x-goog-cloud-target-resource": f"//iam.googleapis.com/projects/{project_number}/locations/global/workloadIdentityPools/{pool_id}/providers/{provider_id}"
        })

    SigV4Auth(boto3.Session().get_credentials(), "sts", "us-east-1").add_auth(request)

    # Create token from signed request.
    token = {
        "url": request.url,
        "method": request.method,
        "headers": []
    }
    for key, value in request.headers.items():
        token["headers"].append({"key": key, "value": value})

    # The token lets workload identity federation verify the identity without revealing the AWS secret access key.
    aws_token = urllib.parse.quote(json.dumps(token))
    print("\naws access token\n", aws_token)
    return aws_token

# Use the Security Token Service API to exchange the credential against a short-lived access token:
def get_gcp_credential(token: str, project_number: str, pool_id: str, provider_id: str) -> str:
    url = 'https://sts.googleapis.com/v1/token'
    headers={'Content-Type':'application/json'}

    payload = """{
                "audience"           : "//iam.googleapis.com/projects/%s/locations/global/workloadIdentityPools/%s/providers/%s",
                "grantType"          : "urn:ietf:params:oauth:grant-type:token-exchange",
                "requestedTokenType" : "urn:ietf:params:oauth:token-type:access_token",
                "scope"              : "https://www.googleapis.com/auth/cloud-platform",
                "subjectTokenType"   : "urn:ietf:params:aws:token-type:aws4_request",
                "subjectToken"       : "%s"
            }
            """ % (project_number, pool_id, provider_id, token)

    response = requests.post(url, headers=headers, data=payload)

    data = response.json()
    print("\nget_gcp_credential access token\n", data["access_token"])
    return data["access_token"]


# Use the token from the Security Token Service to invoke the generateAccessToken method of the IAM Service Account Credentials API to obtain an access token
def get_gcp_serviceaccount_token(gcp_sts_token: str, service_account: str, project_id: str) -> str:
    url = 'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/%s@%s.iam.gserviceaccount.com:generateAccessToken' % (service_account, project_id)
    headers={'Content-Type':'application/json',
               'Authorization': 'Bearer {}'.format(gcp_sts_token)}

    payload = """{
                "scope": [ "https://www.googleapis.com/auth/cloud-platform" ]
            }
            """

    response = requests.post(url, headers=headers, data=payload)

    data = response.json()
    print("\nget_gcp_serviceaccount_token access token\n", data["accessToken"])
    return data["accessToken"]
    

def detect_image_labels(access_token: str) -> None:
    image_url= 'https://storage.googleapis.com/cloud-samples-data/vision/using_curl/shanghai.jpeg'
    url = 'https://content-vision.googleapis.com/v1/images:annotate'
    headers={'Content-Type':'application/json',
               'Authorization': 'Bearer {}'.format(access_token)}
    payload = """{
                  "requests": [
                    {
                      "image": {
                        "source": {
                          "imageUri": "%s"
                        }
                      },
                      "features": [
                        {
                          "maxResults": "5",
                          "type": "LABEL_DETECTION"
                        },
                      ]
                    }
                  ]
                }
            """ % image_url
    
    response = requests.post(url, headers=headers, data=payload)
    data = response.json()
    print('\n########## Showing access to Vision API data ##########')
    print('Labels (and confidence score):')
    for label in data["responses"][0]["labelAnnotations"]:
      print(label["description"],"({:.2%})".format(label["score"]))

def lambda_handler(event=None, context=None):
    print("Running Workload Identity Federation File")
    aws_token = create_token_aws(project_number, pool_id, provider_id)
    gcp_sts_token = get_gcp_credential(aws_token, project_number, pool_id, provider_id)
    access_token =  get_gcp_serviceaccount_token(gcp_sts_token, service_account, project_id)
    detect_image_labels(access_token)