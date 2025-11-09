"""Database initialization and utilities for Firestore."""

from __future__ import annotations

import json
import os
from typing import Optional

from google.cloud import firestore
from google.oauth2 import service_account


class FirestoreClient:
    """Singleton Firestore client wrapper."""
    
    _instance: Optional[firestore.Client] = None
    
    @classmethod
    def get_client(cls) -> firestore.Client:
        """
        Get or create Firestore client.
        
        On Cloud Run: uses Application Default Credentials (no JSON key needed).
        Locally / other hosts: fall back to FIREBASE_SERVICE_ACCOUNT_JSON.
        """
        if cls._instance is None:
            gcp_project = (
                os.environ.get("GOOGLE_CLOUD_PROJECT")
                or os.environ.get("GCLOUD_PROJECT")
                or os.environ.get("FIREBASE_PROJECT_ID")
            )
            svc_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

            if svc_json and not gcp_project:
                info = json.loads(svc_json)
                creds = service_account.Credentials.from_service_account_info(info)
                cls._instance = firestore.Client(project=info["project_id"], credentials=creds)
            else:
                cls._instance = firestore.Client(project=gcp_project)
        
        return cls._instance
    
    @classmethod
    def reset_client(cls) -> None:
        """Reset the client instance. This is useful for testing."""
        cls._instance = None


def get_firestore() -> firestore.Client:
    """Get Firestore client instance."""
    return FirestoreClient.get_client()


def init_database() -> None:
    """Initialize Firestore (no-op, collections are created on first write)."""
    client = get_firestore()
    print(f"[INFO] Firestore client initialized for project: {client.project}")


def reset_database() -> None:
    """
    Delete all documents in main collections (WARNING: deletes all data!).
    This is a destructive operation.
    """
    client = get_firestore()
    collections = ["employees", "shifts", "assignments", "feedback", "weeks"]
    
    for collection_name in collections:
        collection_ref = client.collection(collection_name)
        batch = client.batch()
        count = 0
        
        for doc in collection_ref.stream():
            batch.delete(doc.reference)
            count += 1
            
            # Commit in batches of 500 (Firestore limit)
            if count % 500 == 0:
                batch.commit()
                batch = client.batch()
        
        # Commit remaining deletes
        if count % 500 != 0:
            batch.commit()
        
        print(f"[WARN] Deleted {count} documents from {collection_name}")
    
    print(f"[WARN] Database reset complete")


# Compatibility functions that maintain the Session interface for gradual migration
def get_session(db_url: str = None):
    """
    Get Firestore client. This maintains compatibility with the Session interface.
    The db_url parameter is ignored but kept for backwards compatibility.
    """
    return get_firestore()

