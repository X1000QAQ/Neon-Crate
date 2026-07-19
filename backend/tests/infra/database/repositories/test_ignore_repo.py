import json
import os
import tempfile
import unittest

from app.infra.database.repositories.ignore_repo import IgnoreRepo


class IgnoreRepoTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = IgnoreRepo(data_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_file_rule_matches_only_the_exact_file(self):
        result = self.repo.create_rule("file", ["/library/movies/Example.mkv"])

        self.assertTrue(result["created"])
        self.assertEqual("file", result["rule"]["scope"])
        self.assertIsNotNone(self.repo.match("/library/movies/Example.mkv"))
        self.assertIsNone(self.repo.match("/library/movies/Example-2.mkv"))

    def test_directory_rule_matches_descendants_but_not_prefix_siblings(self):
        self.repo.create_rule("directory", [
            "/library/tv/Example Show/Season 1/S01E01.mkv",
            "/library/tv/Example Show/Season 2/S02E01.mkv",
        ])

        rule = self.repo.match("/library/tv/Example Show/Season 3/S03E01.mkv")
        self.assertIsNotNone(rule)
        self.assertEqual("directory", rule["scope"])
        self.assertEqual("/library/tv/Example Show", rule["path"])
        self.assertIsNone(self.repo.match("/library/tv/Example Showcase/S01E01.mkv"))

    def test_duplicate_and_covered_rules_do_not_create_redundant_entries(self):
        first = self.repo.create_rule("directory", ["/library/tv/Example/Season 1/E01.mkv"])
        duplicate = self.repo.create_rule("directory", ["/library/tv/Example/Season 1/E02.mkv"])
        covered = self.repo.create_rule("file", ["/library/tv/Example/Season 1/E03.mkv"])

        self.assertTrue(first["created"])
        self.assertFalse(duplicate["created"])
        self.assertFalse(covered["created"])
        self.assertEqual(first["rule"]["id"], duplicate["rule"]["id"])
        self.assertEqual(first["rule"]["id"], covered["rule"]["id"])
        self.assertEqual(1, len(self.repo.list_rules()))

    def test_parent_directory_rule_folds_existing_descendants(self):
        first = self.repo.create_rule("file", ["/library/tv/Example/Season 1/E01.mkv"])
        second = self.repo.create_rule("directory", ["/library/tv/Example/Season 2/E01.mkv"])
        parent = self.repo.create_rule("directory", [
            "/library/tv/Example/Season 1/E01.mkv",
            "/library/tv/Example/Season 2/E01.mkv",
        ])

        self.assertTrue(first["created"])
        self.assertTrue(second["created"])
        self.assertTrue(parent["created"])
        self.assertEqual("/library/tv/Example", parent["rule"]["path"])
        self.assertCountEqual(
            [first["rule"]["id"], second["rule"]["id"]],
            parent["removed_rule_ids"],
        )
        self.assertEqual([parent["rule"]], self.repo.list_rules())

    def test_remove_uses_rule_id_and_persists_valid_json(self):
        result = self.repo.create_rule("file", ["/library/movies/Example.mkv"])
        self.assertTrue(self.repo.delete_rule(result["rule"]["id"]))
        self.assertFalse(self.repo.delete_rule(result["rule"]["id"]))
        self.assertEqual([], self.repo.list_rules())

        with open(os.path.join(self.temp_dir.name, "ignore_rules.json"), encoding="utf-8") as rule_file:
            payload = json.load(rule_file)
        self.assertEqual(1, payload["version"])
        self.assertEqual([], payload["rules"])


if __name__ == "__main__":
    unittest.main()
