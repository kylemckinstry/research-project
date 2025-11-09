import json, os
from google.cloud import firestore
from google.oauth2 import service_account

def get_firestore():
    """
    On Cloud Run: uses Application Default Credentials (no JSON key needed).
    Locally / other hosts: fall back to FIREBASE_SERVICE_ACCOUNT_JSON.
    """
    gcp_project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or os.environ.get("FIREBASE_PROJECT_ID")
    )
    svc_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

    if svc_json and not gcp_project:
        info = json.loads(svc_json)
        creds = service_account.Credentials.from_service_account_info(info)
        return firestore.Client(project=info["project_id"], credentials=creds)

    return firestore.Client(project=gcp_project)
