"""Shared error types. Owner: Person 3. The API maps these to the Error contract (shared/contracts/README.md section 4)."""


class UpstreamError(Exception):
    """An external integration failed. integration is one of: matterport, vexcel, costar_kit, ebewe, bedrock."""

    def __init__(self, integration: str, retryable: bool, message: str, http_status: int | None = None):
        super().__init__(message)
        self.integration = integration
        self.retryable = retryable
        self.message = message
        self.http_status = http_status

    @property
    def code(self) -> str:
        if self.http_status in (401, 403):
            return "upstream_auth"
        return "upstream_unavailable"


class AuditCancelled(Exception):
    """Raised inside long-running tools when the user cancels the audit."""
