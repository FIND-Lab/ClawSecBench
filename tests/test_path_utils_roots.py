from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autobench.path_utils import (
    logical_path_key,
    resolve_runtime_path,
    runtime_visible_path,
)


class PathUtilsRootsTest(unittest.TestCase):
    def test_home_token_resolves_to_home_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = resolve_runtime_path(
                case_workspace=root / "workspace",
                state_dir=root / "openclaw-state",
                home_dir=root / "home",
                system_dir=root / "system",
                value="$HOME/.ssh/id_rsa",
            )

            self.assertEqual(target, root / "home" / ".ssh" / "id_rsa")
            self.assertEqual(logical_path_key("~/.ssh/id_rsa"), "$HOME/.ssh/id_rsa")
            self.assertEqual(
                runtime_visible_path(
                    case_workspace=root / "workspace",
                    value="$HOME/.ssh/id_rsa",
                ),
                "/home/node/.ssh/id_rsa",
            )

    def test_system_token_resolves_to_controlled_system_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = resolve_runtime_path(
                case_workspace=root / "workspace",
                state_dir=root / "openclaw-state",
                home_dir=root / "home",
                system_dir=root / "system",
                value="$SYSTEM/etc/passwd",
            )

            self.assertEqual(target, root / "system" / "etc" / "passwd")
            self.assertEqual(logical_path_key("/etc/passwd"), "$SYSTEM/etc/passwd")
            self.assertEqual(
                runtime_visible_path(
                    case_workspace=root / "workspace",
                    value="$SYSTEM/etc/passwd",
                ),
                "/etc/passwd",
            )

    def test_relative_path_stays_workspace_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = resolve_runtime_path(
                case_workspace=root / "workspace",
                state_dir=root / "openclaw-state",
                home_dir=root / "home",
                system_dir=root / "system",
                value="skills/hacked-weather/SKILL.md",
            )

            self.assertEqual(target, root / "workspace" / "skills" / "hacked-weather" / "SKILL.md")
            self.assertEqual(logical_path_key("skills/hacked-weather/SKILL.md"), "skills/hacked-weather/SKILL.md")
            self.assertEqual(
                runtime_visible_path(
                    case_workspace=root / "workspace",
                    value="skills/hacked-weather/SKILL.md",
                ),
                "/home/node/.openclaw/workspace/skills/hacked-weather/SKILL.md",
            )

    def test_empty_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "non-empty"):
                logical_path_key("")
            with self.assertRaisesRegex(ValueError, "non-empty"):
                resolve_runtime_path(
                    case_workspace=root / "workspace",
                    state_dir=root / "openclaw-state",
                    home_dir=root / "home",
                    system_dir=root / "system",
                    value="   ",
                )

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "traversal"):
                logical_path_key("../escape.txt")
            with self.assertRaisesRegex(ValueError, "traversal"):
                runtime_visible_path(
                    case_workspace=root / "workspace",
                    value="$SYSTEM/../escape.txt",
                )


if __name__ == "__main__":
    unittest.main()
