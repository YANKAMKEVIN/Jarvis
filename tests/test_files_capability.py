import unittest

from jarvis.capabilities.files import FilesCapability
from jarvis.security import SecurityDecision
from jarvis.tools.filesystem import FileSystemError


class RecordingSecurity:
    def __init__(self, allowed=True, requires_confirmation=False):
        self.allowed = allowed
        self.requires_confirmation = requires_confirmation
        self.intents = []

    def evaluate(self, intent):
        self.intents.append(intent)
        return SecurityDecision(
            allowed=self.allowed,
            requires_confirmation=self.requires_confirmation,
            reason="test security",
        )


class RecordingFileSystemTools:
    def __init__(self, error=None, mutation_state=None):
        self.error = error
        self.mutation_state = mutation_state or {
            "path": "/Users/test/Documents/New",
            "destination": "/Users/test/Documents/New",
            "previous_path": "/Users/test/Documents/Old",
            "command_executed": True,
            "state_confirmed": True,
        }
        self.calls = []

    def _raise_if_needed(self):
        if self.error is not None:
            raise self.error

    def list_files(self, path=None):
        self.calls.append(("list_files", path))
        self._raise_if_needed()
        return {
            "path": "/Users/test",
            "results": [],
            "result_count": 0,
            "truncated": False,
        }

    def find_files(self, query, path=None):
        self.calls.append(("find_files", query, path))
        self._raise_if_needed()
        return {
            "query": query,
            "path": "/Users/test",
            "results": [{"path": "/Users/test/report.pdf", "name": "report.pdf"}],
            "result_count": 1,
            "truncated": False,
        }

    def get_file_info(self, path):
        self.calls.append(("get_file_info", path))
        self._raise_if_needed()
        return {
            "path": path,
            "name": "report.pdf",
            "kind": "file",
            "size_bytes": 12,
            "modified_at": "2026-09-23T12:00:00",
            "is_hidden": False,
            "is_symlink": False,
        }

    def open_file(self, path):
        self.calls.append(("open_file", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": False,
        }

    def open_folder(self, path):
        self.calls.append(("open_folder", path))
        self._raise_if_needed()
        return {
            "path": path,
            "command_executed": True,
            "state_confirmed": False,
        }

    def create_folder(self, path):
        self.calls.append(("create_folder", path))
        self._raise_if_needed()
        return dict(self.mutation_state, path=path)

    def rename_file(self, path, new_name):
        self.calls.append(("rename_file", path, new_name))
        self._raise_if_needed()
        return dict(
            self.mutation_state,
            previous_path=path,
            path=f"/Users/test/Documents/{new_name}",
            destination=f"/Users/test/Documents/{new_name}",
        )

    def move_file(self, source, destination):
        self.calls.append(("move_file", source, destination))
        self._raise_if_needed()
        return dict(
            self.mutation_state,
            previous_path=source,
            path=destination,
            destination=destination,
        )


class FilesCapabilityTest(unittest.TestCase):
    def test_list_files_does_not_use_security(self):
        security = RecordingSecurity()
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        result = capability.list_files()

        self.assertTrue(result.ok)
        self.assertEqual(result.data["result_count"], 0)
        self.assertEqual(security.intents, [])
        self.assertEqual(tools.calls, [("list_files", None)])

    def test_find_files_returns_structured_results(self):
        capability = FilesCapability(
            security=RecordingSecurity(),
            filesystem_tools=RecordingFileSystemTools(),
        )

        result = capability.find_files("report", "Documents")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["result_count"], 1)
        self.assertEqual(result.data["results"][0]["name"], "report.pdf")

    def test_get_file_info_returns_metadata(self):
        capability = FilesCapability(
            security=RecordingSecurity(),
            filesystem_tools=RecordingFileSystemTools(),
        )

        result = capability.get_file_info("/Users/test/report.pdf")

        self.assertTrue(result.ok)
        self.assertEqual(result.data["kind"], "file")
        self.assertEqual(result.data["size_bytes"], 12)

    def test_open_file_uses_security_and_preserves_unconfirmed_state(self):
        security = RecordingSecurity()
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        result = capability.open_file("/Users/test/report.pdf")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "open_file")
        self.assertEqual(tools.calls, [("open_file", "/Users/test/report.pdf")])

    def test_open_folder_uses_security(self):
        security = RecordingSecurity()
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        result = capability.open_folder("/Users/test/Documents")

        self.assertTrue(result.ok)
        self.assertEqual(security.intents[0].action, "open_folder")
        self.assertEqual(tools.calls, [("open_folder", "/Users/test/Documents")])

    def test_create_folder_uses_security_and_confirms_state(self):
        security = RecordingSecurity()
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        result = capability.create_folder("/Users/test/Documents/New")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["state_confirmed"])
        self.assertEqual(security.intents[0].action, "create_folder")
        self.assertEqual(
            tools.calls,
            [("create_folder", "/Users/test/Documents/New")],
        )

    def test_rename_and_move_use_security(self):
        security = RecordingSecurity()
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        rename = capability.rename_file("/Users/test/Documents/old.txt", "new.txt")
        move = capability.move_file(
            "/Users/test/Documents/new.txt",
            "/Users/test/Downloads/new.txt",
        )

        self.assertTrue(rename.ok)
        self.assertTrue(move.ok)
        self.assertEqual(
            [intent.action for intent in security.intents],
            ["rename_file", "move_file"],
        )
        self.assertEqual(
            tools.calls,
            [
                ("rename_file", "/Users/test/Documents/old.txt", "new.txt"),
                (
                    "move_file",
                    "/Users/test/Documents/new.txt",
                    "/Users/test/Downloads/new.txt",
                ),
            ],
        )

    def test_security_refusal_prevents_filesystem_mutation(self):
        security = RecordingSecurity(allowed=False)
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        result = capability.move_file("/Users/test/a.txt", "/Users/test/b.txt")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "security_denied")
        self.assertEqual(tools.calls, [])

    def test_security_confirmation_prevents_filesystem_mutation(self):
        security = RecordingSecurity(requires_confirmation=True)
        tools = RecordingFileSystemTools()
        capability = FilesCapability(security=security, filesystem_tools=tools)

        result = capability.rename_file("/Users/test/a.txt", "b.txt")

        self.assertFalse(result.ok)
        self.assertTrue(result.requires_confirmation)
        self.assertEqual(result.error_code, "confirmation_required")
        self.assertEqual(tools.calls, [])

    def test_filesystem_error_preserves_error_code_and_candidates(self):
        error = FileSystemError(
            "Plusieurs chemins correspondent.",
            "ambiguous_path",
            {
                "candidates": [
                    {
                        "path": "/Users/test/Desktop/report.pdf",
                        "name": "report.pdf",
                        "parent": "/Users/test/Desktop",
                        "kind": "file",
                    }
                ]
            },
        )
        capability = FilesCapability(
            security=RecordingSecurity(),
            filesystem_tools=RecordingFileSystemTools(error=error),
        )

        result = capability.open_file("report.pdf")
        payload = result.to_livekit_dict()

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "ambiguous_path")
        self.assertEqual(result.data["candidates"][0]["name"], "report.pdf")
        self.assertEqual(payload["error_code"], "ambiguous_path")
        self.assertIn("candidates", payload)

    def test_unresolved_reference_is_reported(self):
        capability = FilesCapability(
            security=RecordingSecurity(),
            filesystem_tools=RecordingFileSystemTools(
                error=FileSystemError(
                    "Reference non resolue.",
                    "unresolved_reference",
                )
            ),
        )

        result = capability.open_file("ce fichier")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "unresolved_reference")

    def test_command_executed_with_failed_final_verification_is_not_confirmed(self):
        tools = RecordingFileSystemTools(
            mutation_state={
                "path": "/Users/test/Documents/New",
                "command_executed": True,
                "state_confirmed": False,
            }
        )
        capability = FilesCapability(
            security=RecordingSecurity(),
            filesystem_tools=tools,
        )

        result = capability.create_folder("/Users/test/Documents/New")

        self.assertTrue(result.ok)
        self.assertTrue(result.data["command_executed"])
        self.assertFalse(result.data["state_confirmed"])
        self.assertIn("pas pu confirmer", result.message)

    def test_system_error_is_reported(self):
        capability = FilesCapability(
            security=RecordingSecurity(),
            filesystem_tools=RecordingFileSystemTools(
                error=RuntimeError("boom"),
            ),
        )

        result = capability.get_file_info("/Users/test/report.pdf")

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "system_error")


if __name__ == "__main__":
    unittest.main()
