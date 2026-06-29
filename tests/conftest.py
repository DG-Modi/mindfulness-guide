from unittest.mock import MagicMock
import google.auth
import google.auth.credentials
import google.cloud.logging
import google.genai

# Mock google.auth.default to prevent DefaultCredentialsError
mock_creds = MagicMock(spec=google.auth.credentials.Credentials)
mock_creds.token = "mock-token"
mock_creds.valid = True
mock_creds.quota_project_id = "mock-project-id"

def mock_default(scopes=None, request=None):
    return (mock_creds, "mock-project-id")

google.auth.default = mock_default

# Mock google.cloud.logging.Client to avoid actual API calls in tests
mock_logging_client = MagicMock(spec=google.cloud.logging.Client)
google.cloud.logging.Client = MagicMock(return_value=mock_logging_client)

# Intercept google.genai.Client initialization to force vertexai=False
original_client_init = google.genai.Client.__init__

def mocked_client_init(self, *args, **kwargs):
    if kwargs.get("vertexai") is None:
        kwargs["vertexai"] = False
    original_client_init(self, *args, **kwargs)

google.genai.Client.__init__ = mocked_client_init
