"""AWS SigV4 request signing for the MCP client (httpx2 transport).

Inside AgentCore Runtime the agent calls the AgentCore Gateway, which uses IAM
inbound auth (authorizer_type AWS_IAM). Each MCP POST is signed with the runtime
execution role for the service name "bedrock-agentcore". botocore resolves the
credentials (in the runtime they come from the container credential provider).
No network call is made here; signing is local.
"""

from __future__ import annotations

from collections.abc import Generator

import httpx2

# Only these headers are signed. Others may be added or changed by the transport
# after signing; unsigned headers are allowed by SigV4.
_SIGNED = ("host", "content-type")


class SigV4Auth(httpx2.Auth):
    requires_request_body = True

    def __init__(self, region: str, service: str = "bedrock-agentcore", credentials=None):
        self.region = region
        self.service = service
        self._credentials = credentials

    def _frozen(self):
        if self._credentials is None:
            import botocore.session

            creds = botocore.session.Session().get_credentials()
            if creds is None:
                raise RuntimeError("No AWS credentials found for SigV4 signing")
            self._credentials = creds
        c = self._credentials
        return c.get_frozen_credentials() if hasattr(c, "get_frozen_credentials") else c

    def sign(self, request: httpx2.Request) -> None:
        from botocore.auth import SigV4Auth as BotoSigV4
        from botocore.awsrequest import AWSRequest

        headers = {k: v for k, v in request.headers.items() if k.lower() in _SIGNED}
        aws_req = AWSRequest(
            method=request.method, url=str(request.url), data=request.content, headers=headers
        )
        BotoSigV4(self._frozen(), self.service, self.region).add_auth(aws_req)
        for k, v in aws_req.headers.items():
            request.headers[k] = v

    def auth_flow(self, request: httpx2.Request) -> Generator[httpx2.Request, httpx2.Response, None]:
        self.sign(request)
        yield request
