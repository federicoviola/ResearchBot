from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from academic_paper_cli.cli import main
from academic_paper_cli.project_manager import (
    ProjectManagerError,
    create_project,
    get_project_status,
    validate_project_name,
)


class ProjectManagerTests(unittest.TestCase):
    def test_create_project_writes_module_one_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = Path(temporary_directory) / "projects"

            status = create_project("autonomy_blockchain_paper", projects_root)

            self.assertTrue(status.valid)
            self.assertEqual(status.pdf_count, 0)
            self.assertEqual(status.skill_count, 1)

            root = projects_root / "autonomy_blockchain_paper"
            expected_paths = [
                root / "config" / "project.yaml",
                root / "config" / "system_prompt.md",
                root / "config" / "writing_style.md",
                root / "config" / "citation_style.yaml",
                root / "config" / "skills" / "outline_design.md",
                root / "dataset" / "pdf",
                root / "dataset" / "txt",
                root / "dataset" / "metadata",
                root / "dataset" / "index",
                root / "outputs" / "outlines",
                root / "outputs" / "notes",
                root / "outputs" / "logs",
                root / "outputs" / "reports",
                root / "state" / "ingestion_state.json",
                root / "state" / "index_state.json",
                root / "state" / "run_history.json",
            ]
            for path in expected_paths:
                self.assertTrue(path.exists(), str(path))

            config = yaml.safe_load((root / "config" / "project.yaml").read_text())
            self.assertEqual(config["name"], "autonomy_blockchain_paper")
            self.assertFalse(config["grounding"]["allow_external_knowledge"])
            self.assertTrue(config["grounding"]["require_sources"])

            ingestion_state = json.loads(
                (root / "state" / "ingestion_state.json").read_text()
            )
            self.assertEqual(ingestion_state["documents"], {})

    def test_status_reports_missing_items(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = Path(temporary_directory) / "projects"
            create_project("paper", projects_root)
            (projects_root / "paper" / "config" / "system_prompt.md").unlink()

            status = get_project_status("paper", projects_root)

            self.assertFalse(status.valid)
            self.assertEqual(status.missing_count, 1)
            self.assertIn("system_prompt.md", str(status.missing_files[0]))

    def test_project_name_rejects_path_traversal(self) -> None:
        with self.assertRaises(ProjectManagerError):
            validate_project_name("../escape")

    def test_cli_init_project_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            projects_root = Path(temporary_directory) / "projects"

            init_exit = main(
                [
                    "init-project",
                    "--name",
                    "cli_paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )
            status_exit = main(
                [
                    "status",
                    "--project",
                    "cli_paper",
                    "--projects-root",
                    str(projects_root),
                ]
            )

            self.assertEqual(init_exit, 0)
            self.assertEqual(status_exit, 0)


if __name__ == "__main__":
    unittest.main()
