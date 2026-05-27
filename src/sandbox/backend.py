"""LangSmith sandbox backend implementation for deep agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

if TYPE_CHECKING:
    from langsmith.sandbox import Sandbox


class LangSmithBackend(BaseSandbox):
    """LangSmith sandbox backend conforming to SandboxBackendProtocol.

    This implementation inherits all file operation methods from BaseSandbox
    and implements execute(), download_files(), and upload_files() using
    LangSmith's native sandbox API.
    """

    def __init__(self, sandbox: Sandbox, timeout: int = 30 * 60) -> None:
        """Initialize the LangSmithBackend with a sandbox instance.

        Args:
            sandbox: LangSmith Sandbox instance
            timeout: Command execution timeout in seconds (default: 30 minutes)
        """
        self._sandbox = sandbox
        self._timeout = timeout

    @property
    def id(self) -> str:
        """Unique identifier for the sandbox backend."""
        return self._sandbox.name

    def execute(self, command: str) -> ExecuteResponse:
        """Execute a command in the sandbox.

        Args:
            command: Full shell command string to execute.

        Returns:
            ExecuteResponse with combined output, exit code, and truncation flag.
        """
        result = self._sandbox.run(command, timeout=self._timeout)

        # Combine stdout and stderr
        output = result.stdout or ""
        if result.stderr:
            output += "\n" + result.stderr if output else result.stderr

        return ExecuteResponse(
            output=output,
            exit_code=result.exit_code,
            truncated=False,
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files from the LangSmith sandbox.

        Args:
            paths: List of file paths to download.

        Returns:
            List of FileDownloadResponse objects, one per input path.
        """
        responses: list[FileDownloadResponse] = []
        for path in paths:
            content = self._sandbox.read(path)
            responses.append(FileDownloadResponse(path=path, content=content, error=None))
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files to the LangSmith sandbox.

        Args:
            files: List of (path, content) tuples to upload.

        Returns:
            List of FileUploadResponse objects, one per input file.
        """
        responses: list[FileUploadResponse] = []
        for path, content in files:
            self._sandbox.write(path, content)
            responses.append(FileUploadResponse(path=path, error=None))
        return responses
