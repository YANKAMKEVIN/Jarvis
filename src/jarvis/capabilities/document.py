"""Answer questions about a local text document, using the local model.

Reads the file's text (bounded, via the filesystem tools' safe resolver) and
asks the free planner model to answer strictly from that content. Read-only; no
network beyond the local/configured model.
"""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.tools.filesystem import FileSystemError, FileSystemTools


_SYSTEM = (
    "Tu reponds a la question de l'utilisateur UNIQUEMENT a partir du document "
    "fourni. Si la reponse n'y figure pas, dis-le clairement sans inventer. "
    "Reste concis, pour une reponse vocale. Reponds dans la langue de la question."
)


class DocumentCapability:
    def __init__(self, filesystem_tools: FileSystemTools | None = None, model=None):
        self.filesystem_tools = (
            filesystem_tools if filesystem_tools is not None else FileSystemTools()
        )
        self._model = model

    def _get_model(self):
        if self._model is None:
            from jarvis.planner.models import build_planner_model

            self._model = build_planner_model()
        return self._model

    def ask(self, path: str, question: str) -> ToolResult:
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure(
                action="ask_about_document",
                message="La question est obligatoire.",
                error_code="invalid_question",
            )
        try:
            doc = self.filesystem_tools.read_text(path)
        except FileSystemError as error:
            return ToolResult.failure(
                action="ask_about_document",
                message=error.message,
                error_code=error.code or "read_failed",
            )
        except Exception as error:
            return ToolResult.failure(
                action="ask_about_document",
                message=f"Lecture du document impossible : {error}",
                error_code="system_error",
            )

        messages = [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Question : {question.strip()}\n\nDocument ({doc['name']}) :\n{doc['text']}"
                ),
            },
        ]
        try:
            turn = self._get_model().complete(messages, [])
        except Exception as error:
            return ToolResult.failure(
                action="ask_about_document",
                message=f"L'analyse du document a echoue : {error}",
                error_code="model_error",
            )

        answer = (turn.text or "").strip()
        if not answer:
            return ToolResult.failure(
                action="ask_about_document",
                message="Le modele n'a pas renvoye de reponse.",
                error_code="empty_result",
            )
        return ToolResult.success(
            action="ask_about_document",
            message=answer,
            document=doc["name"],
            truncated=doc["truncated"],
        )
