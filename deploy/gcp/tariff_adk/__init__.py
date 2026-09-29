"""TariffAgent ADK package for Vertex AI Agent Runtime. Deploy-ready, not deployed.

Nothing is built at import time: call tariff_adk.agent.build_root_agent() or
build_app(). The default models are Claude on Vertex AI, which bill; local validation
passes scripted models instead (deploy/gcp/local_validation).
"""
