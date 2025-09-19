import os
from azure.storage.blob import BlobServiceClient
from django.conf import settings

class AzureBlobStorage:
    def __init__(self):
        self.connection_string = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        self.container_name = 'f-tracker'
        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        self.container_client = self.blob_service_client.get_container_client(self.container_name)

    def upload_blob(self, file, blob_name):
        self.container_client.upload_blob(blob_name, file)
        return self.get_blob_url(blob_name)

    def get_blob_url(self, blob_name):
        return f"https://{self.blob_service_client.account_name}.blob.core.windows.net/{self.container_name}/{blob_name}"
