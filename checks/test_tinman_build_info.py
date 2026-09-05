#!/usr/bin/env python3
"""Exercise build identity and incremental invalidation in disposable CMake/Git trees."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "cmake/modules/TinManBuildInfo.cmake"


class BuildInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("cmake", "git", "ninja"):
            if shutil.which(tool) is None:
                raise RuntimeError(f"{tool} is required for the build-identity tests")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tinman build identity ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.build = self.root / "build"
        self.env = os.environ.copy()
        self.env.pop("git_commit_hash", None)
        self.env.pop("GIT_DIR", None)
        self.env.pop("GIT_WORK_TREE", None)
        self.env["LC_ALL"] = "C"
        self.write_fixture(self.source)

    def run_command(self, *args, cwd=None, expect_success=True):
        result = subprocess.run(
            [str(arg) for arg in args], cwd=cwd, env=self.env,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        if expect_success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def write_fixture(self, source):
        (source / "CMakeLists.txt").write_text(
            'cmake_minimum_required(VERSION 3.13)\n'
            'project(TinManBuildIdentity LANGUAGES CXX)\n'
            'include(revision.cmake)\n'
            f'include("{MODULE.as_posix()}")\n'
            'tinman_configure_build_info("${CMAKE_CURRENT_SOURCE_DIR}" '
            '"${CMAKE_CURRENT_BINARY_DIR}/TinManBuildInfo.hpp")\n'
            'add_executable(identity core.cpp identity.cpp)\n'
            'target_include_directories(identity PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")\n',
            encoding="utf-8",
        )
        (source / "revision.cmake").write_text('set(TINMANX1_REVISION "fixture.1")\n', encoding="utf-8")
        (source / "core.cpp").write_text('int core_value() { return 42; }\n', encoding="utf-8")
        (source / "identity.cpp").write_text(
            '#include "TinManBuildInfo.hpp"\n#include <iostream>\n'
            'int core_value();\nint main() { std::cout << TINMANX1_REVISION << " " '
            '<< GIT_COMMIT_HASH << " " << core_value(); }\n', encoding="utf-8",
        )

    def git(self, *args, source=None):
        return self.run_command("git", *args, cwd=source or self.source).strip()

    def init_git(self):
        self.git("init", "--template=", "-b", "fixture")
        self.git("config", "user.name", "TinManX1 Build Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.root / "no-hooks"))
        self.git("add", ".")
        self.git("commit", "-m", "Initial generated fixture")

    def configure(self, expect_success=True):
        return self.run_command("cmake", "-S", self.source, "-B", self.build, "-G", "Ninja",
                                expect_success=expect_success)

    def compile(self):
        return self.run_command("cmake", "--build", self.build, "--parallel", "2")

    def executable_output(self):
        suffix = ".exe" if os.name == "nt" else ""
        return self.run_command(self.build / f"identity{suffix}").strip()

    def object_time(self, name):
        matches = [p for p in self.build.rglob(f"{name}.cpp.*") if p.suffix in (".o", ".obj")]
        self.assertEqual(len(matches), 1, matches)
        return matches[0].stat().st_mtime_ns

    def assert_metadata_only_rebuild(self, mutate, expected):
        core_before = self.object_time("core")
        identity_before = self.object_time("identity")
        time.sleep(0.05)
        mutate()
        self.compile()
        self.assertEqual(self.executable_output(), expected())
        self.assertEqual(self.object_time("core"), core_before, "Unrelated core source recompiled")
        self.assertGreater(self.object_time("identity"), identity_before)
        self.assertIn("no work to do", self.compile())

    def test_archive_fallback_and_noop_configuration(self):
        self.configure()
        self.compile()
        self.assertEqual(self.executable_output(), "fixture.1 0000000 42")
        header = self.build / "TinManBuildInfo.hpp"
        before = header.stat().st_mtime_ns
        self.configure()
        self.assertEqual(header.stat().st_mtime_ns, before)
        self.assertIn("no work to do", self.compile())

    def test_archive_explicit_commit_and_revision_only_rebuild(self):
        self.env["git_commit_hash"] = "ABCDEF0123456789abcdef0123456789abcdef0123"
        self.configure()
        self.compile()
        self.assertEqual(self.executable_output(), "fixture.1 abcdef0 42")
        self.assert_metadata_only_rebuild(
            lambda: (self.source / "revision.cmake").write_text(
                'set(TINMANX1_REVISION "fixture.2")\n', encoding="utf-8"),
            lambda: "fixture.2 abcdef0 42",
        )

    def test_bad_explicit_hash_is_rejected(self):
        for value in ('bad"value', "abc", "-invalid", "a" * 65):
            with self.subTest(value=value):
                self.env["git_commit_hash"] = value
                self.assertIn("hexadecimal commit ID", self.configure(expect_success=False))

    def test_checkout_commit_and_detached_head_refresh(self):
        self.init_git()
        original = self.git("rev-parse", "--short", "HEAD")
        self.configure()
        self.compile()
        self.assertEqual(self.executable_output(), f"fixture.1 {original} 42")
        self.assert_metadata_only_rebuild(
            lambda: self.git("commit", "--allow-empty", "-m", "Second generated fixture"),
            lambda: f'fixture.1 {self.git("rev-parse", "--short", "HEAD")} 42',
        )
        self.assert_metadata_only_rebuild(
            lambda: self.git("checkout", "--detach", original),
            lambda: f"fixture.1 {original} 42",
        )

    def test_packed_branch_without_reflog_refreshes_when_loose_ref_appears(self):
        self.init_git()
        self.git("config", "core.logAllRefUpdates", "false")
        self.git("pack-refs", "--all", "--prune")
        self.assertFalse((self.source / ".git/refs/heads/fixture").exists())
        self.configure()
        self.compile()
        self.assert_metadata_only_rebuild(
            lambda: self.git("commit", "--allow-empty", "-m", "New loose branch ref"),
            lambda: f'fixture.1 {self.git("rev-parse", "--short", "HEAD")} 42',
        )

    def test_linked_worktree_refreshes_without_rebuilding_core(self):
        self.init_git()
        worktree = self.root / "linked worktree"
        self.git("worktree", "add", "-b", "linked", worktree)
        self.source = worktree
        self.assertTrue((worktree / ".git").is_file())
        self.configure()
        self.compile()
        self.assert_metadata_only_rebuild(
            lambda: self.git("commit", "--allow-empty", "-m", "Worktree-only commit"),
            lambda: f'fixture.1 {self.git("rev-parse", "--short", "HEAD")} 42',
        )

    def test_explicit_checkout_hash_is_verified(self):
        self.init_git()
        self.env["git_commit_hash"] = self.git("rev-parse", "HEAD")
        self.configure()
        self.compile()
        self.assertEqual(self.executable_output(),
                         f'fixture.1 {self.git("rev-parse", "--short", "HEAD")} 42')
        self.env["git_commit_hash"] = "1234567890abcdef1234567890abcdef12345678"
        self.assertIn("does not identify a commit", self.configure(expect_success=False))

    def test_shallow_ci_checkout_accepts_declared_full_commit(self):
        self.init_git()
        parent = self.git("rev-parse", "HEAD")
        self.git("commit", "--allow-empty", "-m", "Shallow tip")
        shallow = self.root / "shallow checkout"
        self.git("clone", "--depth=1", self.source.as_uri(), shallow)
        self.source = shallow
        self.assertEqual(self.git("rev-parse", "--is-shallow-repository"), "true")
        self.env["git_commit_hash"] = parent
        self.configure()
        self.compile()
        self.assertEqual(self.executable_output(), f"fixture.1 {parent[:7]} 42")
        self.env["git_commit_hash"] = "badabcd"
        self.assertIn("does not identify a commit", self.configure(expect_success=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
