from app.adapters.llm.azure_apim_provider import AzureAPIMProvider
from app.adapters.llm.openai_provider import OpenAIProvider

def get_llm_provider():
	from app.core.config import get_settings
	s = get_settings()
	# If llm_provider explicitly 'azure' but endpoint isn't native, prefer APIM provider
	if s.llm_provider == "azure" and s.azure_openai_endpoint and "azure-api.net" in s.azure_openai_endpoint:
		return AzureAPIMProvider()
	return OpenAIProvider()

