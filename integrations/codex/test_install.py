import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

import install


ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "target" / "debug" / "contextspindle"


class InstallerTests(unittest.TestCase):
    def test_global_rule_preserves_other_instructions_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AGENTS.md"
            path.write_text("# Existing personal instructions\n\nKeep this rule.\n")
            install.install_rule(path)
            first = path.read_text()
            install.install_rule(path)
            self.assertEqual(path.read_text(), first)
            self.assertIn("Keep this rule.", first)
            self.assertEqual(first.count(install.START), 1)

    def test_mcp_approves_only_read_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            wrapper = home / "skills" / install.SKILL / "scripts" / "contextspindle"

            def fake_run(*args, env):
                if args[2] == "get":
                    return subprocess.CompletedProcess(args, 1, "", "not found")
                (home / "config.toml").write_text(
                    f'[mcp_servers.contextspindle]\ncommand = "{wrapper}"\nargs = ["mcp"]\n'
                )
                return subprocess.CompletedProcess(args, 0, "", "")

            with patch.object(install, "run", side_effect=fake_run):
                install.register_mcp(home, wrapper)
            config = tomllib.loads((home / "config.toml").read_text())
            tools = config["mcp_servers"]["contextspindle"]["tools"]
            self.assertEqual(set(tools), set(install.READ_TOOLS))
            self.assertTrue(all(value["approval_mode"] == "approve" for value in tools.values()))
            self.assertNotIn("contextspindle_task_update", tools)

    @unittest.skipUnless(BINARY.is_file(), "build contextspindle debug binary first")
    def test_installed_wrapper_recovers_a_task_in_a_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            command = [
                sys.executable, str(Path(install.__file__)),
                "--codex-home", str(home), "--binary", str(BINARY), "--skip-mcp",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual((home / "AGENTS.md").read_text().count(install.START), 1)
            wrapper = home / "skills" / install.SKILL / "scripts" / "contextspindle"
            env = dict(os.environ, CODEX_HOME=str(home))
            created = subprocess.run(
                [str(wrapper), "task", "create", "Keep release goal", "--criteria", "Tests pass"],
                check=True, capture_output=True, text=True, env=env,
            )
            import json
            task_id = json.loads(created.stdout)["id"]
            subprocess.run(
                [str(wrapper), "task", "update", task_id, "--next", "Run final tests"],
                check=True, capture_output=True, text=True, env=env,
            )
            context = subprocess.run(
                [str(wrapper), "task", "context", task_id, "2048"],
                check=True, capture_output=True, text=True, env=env,
            ).stdout
            self.assertIn("Keep release goal", context)
            self.assertIn("Run final tests", context)
            self.assertIn("Omitted optional items: 0", context)


if __name__ == "__main__":
    unittest.main()
