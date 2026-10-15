import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.tools.filesystem import FileSystemError, FileSystemTools, PathResolver


class FileSystemToolsTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tempdir.name).resolve()
        (self.home / "Desktop").mkdir()
        (self.home / "Downloads").mkdir()
        (self.home / "Documents").mkdir()
        self.tools = FileSystemTools(
            resolver=PathResolver(home=self.home),
            list_limit=3,
            find_limit=3,
            max_find_depth=2,
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def write_file(self, relative_path, content="test"):
        path = self.home / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_list_directory_returns_visible_entries(self):
        self.write_file("Documents/rapport.txt")
        self.write_file("Documents/.cache")

        result = self.tools.list_files("Documents")

        self.assertEqual(result["path"], str(self.home / "Documents"))
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["name"], "rapport.txt")
        self.assertFalse(result["results"][0]["is_hidden"])

    def test_list_empty_directory(self):
        result = self.tools.list_files("Downloads")

        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["results"], [])
        self.assertFalse(result["truncated"])

    def test_list_missing_path_raises_explicit_error(self):
        with self.assertRaises(FileSystemError) as context:
            self.tools.list_files("Documents/absent")

        self.assertEqual(context.exception.code, "path_not_found")

    def test_list_file_path_raises_not_a_directory(self):
        self.write_file("Documents/file.txt")

        with self.assertRaises(FileSystemError) as context:
            self.tools.list_files("Documents/file.txt")

        self.assertEqual(context.exception.code, "not_a_directory")

    def test_unicode_spaces_and_apostrophes_are_preserved(self):
        path = self.write_file("Documents/Résumé d'été.txt")

        info = self.tools.get_file_info(str(path))

        self.assertEqual(info["name"], "Résumé d'été.txt")
        self.assertEqual(info["path"], str(path))

    def test_find_exact_partial_and_extension(self):
        self.write_file("Documents/rapport.pdf")
        self.write_file("Documents/notes.txt")

        exact = self.tools.find_files("rapport.pdf", "Documents")
        partial = self.tools.find_files("appo", "Documents")
        extension = self.tools.find_files("pdf", "Documents")

        self.assertEqual(exact["result_count"], 1)
        self.assertEqual(partial["result_count"], 1)
        self.assertEqual(extension["result_count"], 1)
        self.assertEqual(extension["results"][0]["name"], "rapport.pdf")

    def test_find_returns_no_results(self):
        result = self.tools.find_files("missing", "Documents")

        self.assertEqual(result["result_count"], 0)
        self.assertEqual(result["results"], [])

    def test_find_is_bounded_and_truncated(self):
        for index in range(5):
            self.write_file(f"Documents/report-{index}.txt")

        result = self.tools.find_files("report", "Documents")

        self.assertEqual(result["result_count"], 3)
        self.assertTrue(result["truncated"])

    def test_ambiguous_path_returns_candidates(self):
        self.write_file("Desktop/rapport.pdf")
        self.write_file("Downloads/rapport.pdf")

        with self.assertRaises(FileSystemError) as context:
            self.tools.open_file("rapport.pdf")

        self.assertEqual(context.exception.code, "ambiguous_path")
        self.assertEqual(len(context.exception.data["candidates"]), 2)

    def test_get_file_info_file_directory_and_symlink(self):
        file_path = self.write_file("Documents/file.txt")
        folder_path = self.home / "Documents"
        symlink_path = self.home / "Documents/link.txt"
        symlink_path.symlink_to(file_path)

        file_info = self.tools.get_file_info(str(file_path))
        folder_info = self.tools.get_file_info(str(folder_path))
        symlink_info = self.tools.get_file_info(str(symlink_path))

        self.assertEqual(file_info["kind"], "file")
        self.assertEqual(folder_info["kind"], "directory")
        self.assertEqual(symlink_info["kind"], "symlink")
        self.assertTrue(symlink_info["is_symlink"])

    def test_create_folder_confirms_final_state(self):
        target = self.home / "Documents/New Folder"

        result = self.tools.create_folder(str(target))

        self.assertTrue(result["command_executed"])
        self.assertTrue(result["state_confirmed"])
        self.assertTrue(target.is_dir())

    def test_create_folder_collision_is_refused(self):
        target = self.home / "Documents/Existing"
        target.mkdir()

        with self.assertRaises(FileSystemError) as context:
            self.tools.create_folder(str(target))

        self.assertEqual(context.exception.code, "already_exists")

    def test_rename_confirms_final_state(self):
        source = self.write_file("Documents/old.txt")

        result = self.tools.rename_file(str(source), "new.txt")

        self.assertTrue(result["state_confirmed"])
        self.assertFalse(source.exists())
        self.assertTrue((self.home / "Documents/new.txt").exists())

    def test_rename_collision_is_refused_without_mutation(self):
        source = self.write_file("Documents/old.txt")
        destination = self.write_file("Documents/new.txt")

        with self.assertRaises(FileSystemError) as context:
            self.tools.rename_file(str(source), destination.name)

        self.assertEqual(context.exception.code, "destination_exists")
        self.assertTrue(source.exists())
        self.assertTrue(destination.exists())

    def test_move_confirms_final_state(self):
        source = self.write_file("Documents/file.txt")
        destination = self.home / "Downloads/file.txt"

        result = self.tools.move_file(str(source), str(destination))

        self.assertTrue(result["state_confirmed"])
        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())

    def test_move_collision_source_equals_destination_and_missing_parent(self):
        source = self.write_file("Documents/file.txt")
        destination = self.write_file("Downloads/file.txt")

        with self.assertRaises(FileSystemError) as collision:
            self.tools.move_file(str(source), str(destination))

        with self.assertRaises(FileSystemError) as same:
            self.tools.move_file(str(source), str(source))

        with self.assertRaises(FileSystemError) as missing_parent:
            self.tools.move_file(str(source), str(self.home / "Nope/file.txt"))

        self.assertEqual(collision.exception.code, "destination_exists")
        self.assertEqual(same.exception.code, "same_path")
        self.assertEqual(
            missing_parent.exception.code,
            "destination_parent_missing",
        )

    def test_move_into_existing_folder_keeps_source_name(self):
        source = self.write_file("Documents/file.txt")
        (self.home / "Downloads").mkdir(exist_ok=True)

        result = self.tools.move_file(str(source), str(self.home / "Downloads"))

        self.assertTrue(result["state_confirmed"])
        self.assertEqual(result["destination"], str(self.home / "Downloads/file.txt"))
        self.assertFalse(source.exists())
        self.assertTrue((self.home / "Downloads/file.txt").exists())

    def test_move_into_folder_refuses_collision_without_mutation(self):
        source = self.write_file("Documents/file.txt")
        existing = self.write_file("Downloads/file.txt")

        with self.assertRaises(FileSystemError) as context:
            self.tools.move_file(str(source), str(self.home / "Downloads"))

        self.assertEqual(context.exception.code, "destination_exists")
        self.assertTrue(source.exists())
        self.assertTrue(existing.exists())

    def test_move_into_own_parent_or_inside_itself_is_refused(self):
        folder = self.home / "Documents/Projet"
        (folder / "sub").mkdir(parents=True)

        with self.assertRaises(FileSystemError) as same_parent:
            self.tools.move_file(str(folder), str(self.home / "Documents"))

        with self.assertRaises(FileSystemError) as inside:
            self.tools.move_file(str(folder), str(folder / "sub"))

        self.assertEqual(same_parent.exception.code, "same_path")
        self.assertEqual(inside.exception.code, "destination_inside_source")
        self.assertTrue((folder / "sub").is_dir())

    def test_outside_home_and_path_traversal_are_refused(self):
        outside = Path(self.tempdir.name).parent / "outside-jarvis-test.txt"

        with self.assertRaises(FileSystemError) as absolute:
            self.tools.get_file_info(str(outside))

        with self.assertRaises(FileSystemError) as traversal:
            self.tools.create_folder("Documents/../../outside")

        self.assertEqual(absolute.exception.code, "path_not_found")
        self.assertEqual(traversal.exception.code, "outside_home")

    def test_symlink_pointing_outside_home_is_refused_for_mutation(self):
        outside_dir = Path(self.tempdir.name).parent
        symlink_path = self.home / "Documents/outside-link"
        symlink_path.symlink_to(outside_dir)

        with self.assertRaises(FileSystemError) as context:
            self.tools.rename_file(str(symlink_path), "renamed-link")

        self.assertEqual(context.exception.code, "outside_home")
        self.assertTrue(symlink_path.is_symlink())

    def test_permission_denied_is_reported(self):
        with patch("pathlib.Path.iterdir", side_effect=PermissionError("denied")):
            with self.assertRaises(FileSystemError) as context:
                self.tools.list_files("Documents")

        self.assertEqual(context.exception.code, "permission_denied")

    def test_open_file_and_folder_use_macos_open_without_shell(self):
        file_path = self.write_file("Documents/file.txt")
        folder_path = self.home / "Documents"
        completed = Mock(returncode=0, stderr="", stdout="")

        with patch("jarvis.tools.filesystem.subprocess.run", return_value=completed) as run:
            file_result = self.tools.open_file(str(file_path))
            folder_result = self.tools.open_folder(str(folder_path))

        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], ["open", str(file_path)])
        self.assertEqual(run.call_args_list[1].args[0], ["open", str(folder_path)])
        self.assertFalse(file_result["state_confirmed"])
        self.assertFalse(folder_result["state_confirmed"])

    def test_unresolved_reference_is_refused(self):
        with self.assertRaises(FileSystemError) as context:
            self.tools.open_file("ce fichier")

        self.assertEqual(context.exception.code, "unresolved_reference")

    def test_aliases_resolve_to_home_directories(self):
        self.assertEqual(
            self.tools.list_files("Bureau")["path"],
            str(self.home / "Desktop"),
        )
        self.assertEqual(
            self.tools.list_files("Téléchargements")["path"],
            str(self.home / "Downloads"),
        )
        self.assertEqual(self.tools.list_files("maison")["path"], str(self.home))

    def test_bundles_are_reported_but_not_recursed(self):
        bundle = self.home / "Documents/Test.app"
        nested = bundle / "Contents"
        nested.mkdir(parents=True)
        (nested / "inside.txt").write_text("test", encoding="utf-8")

        listed = self.tools.list_files("Documents")
        found = self.tools.find_files("inside", "Documents")

        self.assertEqual(listed["results"][0]["kind"], "bundle")
        self.assertEqual(found["result_count"], 0)


if __name__ == "__main__":
    unittest.main()
