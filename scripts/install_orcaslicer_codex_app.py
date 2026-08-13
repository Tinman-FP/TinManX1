#!/usr/bin/env python3
"""Install a locally built OrcaSlicer bundle as TinManX1.

The installer preserves the TinManX1 app identity and data directory while swapping
in a freshly built OrcaSlicer executable/resources bundle.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path


EXPECTED_TARGET_NAME = "TinManX1"
EXPECTED_BUNDLE_ID = "com.tinmanfp.TinManX1"
UPSTREAM_EXECUTABLE_NAME = "OrcaSlicer"
TARGET_EXECUTABLE_NAME = EXPECTED_TARGET_NAME
DEFAULT_TARGET_APP = Path("/Applications/TinManX1.app")
DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
AUTO_PA_WRAPPER_REL = Path("Contents/Resources/orcaslicer_codex/auto_pa/tinman_auto_pa_postprocess.py")
LEGACY_PREFLIGHT_REL = Path("tools/orca_codex_launch_preflight.py")
GENERATED_RESOURCE_PATTERNS = ("__pycache__", "*.pyc", "*-venv", ".venv", "venv")
BUILD_CONFIGURATIONS = ("Debug", "RelWithDebInfo", "Release")


def repo_defaults() -> tuple[Path, Path]:
    control_root = Path(__file__).resolve().parents[1]
    work_root = control_root.parent
    source_root = work_root / "TinManX1-source-v2.4.2"
    built_apps = [
        source_root / "build" / "arm64" / "OrcaSlicer" / "OrcaSlicer.app",
        source_root / "build" / "arm64" / "src" / "Release" / "OrcaSlicer.app",
        source_root / "build" / "arm64" / "src" / "RelWithDebInfo" / "OrcaSlicer.app",
        source_root / "build" / "arm64" / "src" / "Debug" / "OrcaSlicer.app",
    ]
    built_app = next(
        (app for app in built_apps if (app / "Contents" / "MacOS" / "OrcaSlicer").exists()),
        built_apps[-1],
    )
    return source_root, built_app


def source_build_configuration(source_app: Path) -> str | None:
    """Return a conventional CMake configuration embedded in the app path."""
    path_parts = source_app.resolve(strict=False).parts
    return next((config for config in BUILD_CONFIGURATIONS if config in path_parts), None)


def run(args: list[str]) -> None:
    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)


def copy_optional_file(src: Path, dst: Path) -> None:
    if src.exists():
        if dst.exists() and src.resolve() == dst.resolve():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_optional_tree(src: Path, dst: Path) -> None:
    if src.exists():
        if dst.exists() and src.resolve() == dst.resolve():
            return
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, symlinks=True)


def copy_first_available(candidates: list[Path], dst: Path, *, executable: bool = False) -> None:
    for src in candidates:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if executable:
                dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return


def install_feature_resources(source_root: Path, app: Path) -> None:
    release_root = Path(__file__).resolve().parents[1]
    resources = app / "Contents" / "Resources" / "orcaslicer_codex"
    arc_support = resources / "arc_support"
    sidecars = resources / "sidecars"
    auto_pa = resources / "auto_pa"
    helpers = source_root / "scripts" / "source-helpers"

    copy_optional_file(
        helpers / "orcaslicer_codex_arc_support_inplace_adapter.py",
        arc_support / "orcaslicer_codex_arc_support_inplace_adapter.py",
    )
    copy_optional_file(
        helpers / "orcaslicer_codex_arc_support_transform.py",
        arc_support / "orcaslicer_codex_arc_support_transform.py",
    )
    copy_optional_tree(
        source_root / "resources" / "orcaslicer_codex" / "third_party" / "gpl" / "arc-overhang",
        resources / "third_party" / "gpl" / "arc-overhang",
    )
    copy_optional_tree(
        source_root / "resources" / "orcaslicer_codex" / "auto_pa",
        auto_pa,
    )
    copy_optional_file(
        helpers / "orcaslicer_codex_strength_lens_sidecar.py",
        sidecars / "orcaslicer_codex_strength_lens_sidecar.py",
    )
    copy_optional_file(
        helpers / "orcaslicer_codex_fiber_metadata_sidecar.py",
        sidecars / "orcaslicer_codex_fiber_metadata_sidecar.py",
    )
    copy_optional_file(
        source_root / "SoftFever_doc" / "orcaslicer_codex_feature_attribution.md",
        resources / "attribution" / "orcaslicer_codex_feature_attribution.md",
    )
    copy_first_available(
        [
            source_root / "scripts" / "repair_tinmanx1_bambu_lan_bindings.py",
            release_root / "scripts" / "source-helpers" / "repair_tinmanx1_bambu_lan_bindings.py",
        ],
        resources / "tools" / "repair_bambu_lan_bindings.py",
        executable=True,
    )
    copy_first_available(
        [
            source_root / "scripts" / "repair_tinmanx1_prusalink_bindings.py",
            source_root / "scripts" / "source-helpers" / "repair_tinmanx1_prusalink_bindings.py",
            release_root / "scripts" / "source-helpers" / "repair_tinmanx1_prusalink_bindings.py",
        ],
        resources / "tools" / "repair_prusalink_bindings.py",
        executable=True,
    )
    copy_first_available(
        [
            source_root / "scripts" / "sync_tinmanx1_bambu_network_plugin.py",
            source_root / "scripts" / "source-helpers" / "sync_tinmanx1_bambu_network_plugin.py",
            release_root / "scripts" / "source-helpers" / "sync_tinmanx1_bambu_network_plugin.py",
        ],
        resources / "tools" / "sync_bambu_network_plugin.py",
        executable=True,
    )


def install_auto_pa_profile_hook(source_root: Path, target_app: Path, app_support: Path) -> None:
    helper = source_root / "scripts" / "source-helpers" / "tinman_auto_pa_profile_hook.py"
    wrapper = target_app / AUTO_PA_WRAPPER_REL
    if not helper.exists():
        return
    run(
        [
            sys.executable,
            str(helper),
            "--datadir",
            str(app_support),
            "--wrapper",
            str(wrapper),
            "--include-system",
        ]
    )


def archive_legacy_launch_preflight(app_support: Path) -> Path | None:
    """Disable the old mutable launch repair pipeline without deleting its source."""
    preflight = app_support / LEGACY_PREFLIGHT_REL
    if not preflight.exists():
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = app_support / "_legacy_launch_preflight_archive" / stamp / preflight.name
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(preflight), str(archive))
    return archive


def update_info_plist(app: Path) -> str:
    info_path = app / "Contents" / "Info.plist"
    with info_path.open("rb") as fh:
        info = plistlib.load(fh)

    version = str(info.get("CFBundleShortVersionString") or "2.4.2")
    info["CFBundleName"] = EXPECTED_TARGET_NAME
    info["CFBundleDisplayName"] = EXPECTED_TARGET_NAME
    info["CFBundleIdentifier"] = EXPECTED_BUNDLE_ID
    info["CFBundleExecutable"] = TARGET_EXECUTABLE_NAME
    info["CFBundleShortVersionString"] = version

    with info_path.open("wb") as fh:
        plistlib.dump(info, fh, sort_keys=False)
    return version


def c_string(value: str) -> str:
    return json.dumps(value)


def executable_archs(path: Path) -> list[str]:
    proc = subprocess.run(["lipo", "-archs", str(path)], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return []
    return [arch for arch in proc.stdout.strip().split() if arch]


def write_native_launcher(launcher: Path, real: Path, default_datadir: str) -> None:
    clang = shutil.which("clang") or shutil.which("cc")
    if not clang:
        raise SystemExit("clang/cc is required to build the native TinManX1 macOS launcher")

    source = launcher.with_suffix(".launcher.c")
    source.write_text(
        textwrap.dedent(
            f"""
            #include <errno.h>
            #include <fcntl.h>
            #include <limits.h>
            #include <mach-o/dyld.h>
            #include <spawn.h>
            #include <stdarg.h>
            #include <stdbool.h>
            #include <stdio.h>
            #include <stdlib.h>
            #include <string.h>
            #include <sys/stat.h>
            #include <sys/wait.h>
            #include <unistd.h>

            extern char **environ;

            static const char *DEFAULT_DATADIR = {c_string(default_datadir)};
            static const char *BAMBU_POLICY_ENV = "ORCASLICER_CODEX_BAMBU_PLUGIN_POLICY=allow";
            static const char *BAMBU_REPAIR_MARKER = "repair_bambu_lan_bindings.py";
            static const char *BAMBU_PLUGIN_SYNC_MARKER = "sync_bambu_network_plugin.py";
            static const char *PRUSALINK_REPAIR_MARKER = "repair_prusalink_bindings.py";

            static void copy_string(char *dst, size_t dst_size, const char *src) {{
                if (dst_size == 0) return;
                if (!src) src = "";
                snprintf(dst, dst_size, "%s", src);
            }}

            static bool starts_with(const char *value, const char *prefix) {{
                return strncmp(value, prefix, strlen(prefix)) == 0;
            }}

            static void dirname_inplace(char *path) {{
                char *slash = strrchr(path, '/');
                if (!slash) {{
                    copy_string(path, PATH_MAX, ".");
                    return;
                }}
                if (slash == path) {{
                    slash[1] = '\\0';
                    return;
                }}
                *slash = '\\0';
            }}

            static void join_path(char *dst, size_t dst_size, const char *base, const char *rel) {{
                if (!base || !*base) {{
                    copy_string(dst, dst_size, rel);
                    return;
                }}
                size_t len = strlen(base);
                snprintf(dst, dst_size, "%s%s%s", base, (len > 0 && base[len - 1] == '/') ? "" : "/", rel);
            }}

            static void expand_default_datadir(char *dst, size_t dst_size) {{
                const char *env_datadir = getenv("ORCASLICER_CODEX_DATADIR");
                if (env_datadir && *env_datadir) {{
                    copy_string(dst, dst_size, env_datadir);
                    return;
                }}
                if (starts_with(DEFAULT_DATADIR, "~/")) {{
                    const char *home = getenv("HOME");
                    if (home && *home) {{
                        join_path(dst, dst_size, home, DEFAULT_DATADIR + 2);
                        return;
                    }}
                }}
                copy_string(dst, dst_size, DEFAULT_DATADIR);
            }}

            static void mkdir_p(const char *path) {{
                if (!path || !*path) return;
                char tmp[PATH_MAX];
                copy_string(tmp, sizeof(tmp), path);
                for (char *p = tmp + 1; *p; ++p) {{
                    if (*p == '/') {{
                        *p = '\\0';
                        mkdir(tmp, 0755);
                        *p = '/';
                    }}
                }}
                mkdir(tmp, 0755);
            }}

            static void redirect_to(int fd, const char *path) {{
                int out = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {{
                    dup2(out, fd);
                    close(out);
                }}
            }}

            static void run_python_helper(const char *script, char *const argv[], const char *stdout_path, const char *stderr_path) {{
                if (!script || access(script, F_OK) != 0) return;
                pid_t pid = fork();
                if (pid < 0) return;
                if (pid == 0) {{
                    unsetenv("PYTHONHOME");
                    unsetenv("PYTHONPATH");
                    if (stdout_path) redirect_to(STDOUT_FILENO, stdout_path);
                    if (stderr_path) redirect_to(STDERR_FILENO, stderr_path);
                    execv("/usr/bin/python3", argv);
                    _exit(127);
                }}
                int status = 0;
                waitpid(pid, &status, 0);
            }}

            int main(int argc, char **argv) {{
                char exe_path[PATH_MAX];
                uint32_t size = sizeof(exe_path);
                if (_NSGetExecutablePath(exe_path, &size) != 0) return 126;

                char resolved_exe[PATH_MAX];
                if (!realpath(exe_path, resolved_exe)) copy_string(resolved_exe, sizeof(resolved_exe), exe_path);

                char macos_dir[PATH_MAX];
                copy_string(macos_dir, sizeof(macos_dir), resolved_exe);
                dirname_inplace(macos_dir);

                char real_path[PATH_MAX];
                join_path(real_path, sizeof(real_path), macos_dir, "TinManX1.real");

                char datadir[PATH_MAX];
                expand_default_datadir(datadir, sizeof(datadir));
                mkdir_p(datadir);

                setenv("ORCASLICER_CODEX_DATADIR", datadir, 0);
                if (!getenv("ORCASLICER_CODEX_BAMBU_PLUGIN_POLICY")) {{
                    putenv((char *)BAMBU_POLICY_ENV);
                }}
                unsetenv("PYTHONHOME");
                unsetenv("PYTHONPATH");

                if (!getenv("TINMANX1_SKIP_BAMBU_PLUGIN_SYNC")) {{
                    char helper[PATH_MAX], out[PATH_MAX], err[PATH_MAX];
                    join_path(helper, sizeof(helper), macos_dir, "../Resources/orcaslicer_codex/tools/sync_bambu_network_plugin.py");
                    join_path(out, sizeof(out), datadir, "_tinmanx1_bambu_plugin_sync_last.out");
                    join_path(err, sizeof(err), datadir, "_tinmanx1_bambu_plugin_sync_last.err");
                    char *sync_argv[] = {{"/usr/bin/python3", helper, "--datadir", datadir, NULL}};
                    (void)BAMBU_PLUGIN_SYNC_MARKER;
                    run_python_helper(helper, sync_argv, out, err);
                }}

                if (!getenv("TINMANX1_SKIP_BAMBU_LAN_REPAIR")) {{
                    char helper[PATH_MAX], out[PATH_MAX], err[PATH_MAX];
                    join_path(helper, sizeof(helper), macos_dir, "../Resources/orcaslicer_codex/tools/repair_bambu_lan_bindings.py");
                    join_path(out, sizeof(out), datadir, "_tinmanx1_bambu_lan_repair_last.out");
                    join_path(err, sizeof(err), datadir, "_tinmanx1_bambu_lan_repair_last.err");
                    char *repair_argv[] = {{"/usr/bin/python3", helper, "--datadir", datadir, NULL}};
                    (void)BAMBU_REPAIR_MARKER;
                    run_python_helper(helper, repair_argv, out, err);
                }}

                if (!getenv("TINMANX1_SKIP_PRUSALINK_REPAIR")) {{
                    char helper[PATH_MAX], out[PATH_MAX], err[PATH_MAX];
                    join_path(helper, sizeof(helper), macos_dir, "../Resources/orcaslicer_codex/tools/repair_prusalink_bindings.py");
                    join_path(out, sizeof(out), datadir, "_tinmanx1_prusalink_repair_last.out");
                    join_path(err, sizeof(err), datadir, "_tinmanx1_prusalink_repair_last.err");
                    char *repair_argv[] = {{"/usr/bin/python3", helper, "--datadir", datadir, NULL}};
                    (void)PRUSALINK_REPAIR_MARKER;
                    run_python_helper(helper, repair_argv, out, err);
                }}

                int extra = 2;
                char **real_argv = calloc((size_t)argc + (size_t)extra + 1, sizeof(char *));
                if (!real_argv) return 125;
                real_argv[0] = real_path;
                real_argv[1] = "--datadir";
                real_argv[2] = datadir;
                for (int i = 1; i < argc; ++i) {{
                    real_argv[i + extra] = argv[i];
                }}
                real_argv[argc + extra] = NULL;

                execv(real_path, real_argv);
                perror("execv TinManX1.real");
                return 127;
            }}
            """
        ).strip()
        + "\n"
    )

    cmd = [clang, "-Os", "-mmacosx-version-min=10.13"]
    archs = executable_archs(real)
    for arch in archs:
        cmd.extend(["-arch", arch])
    cmd.extend([str(source), "-o", str(launcher)])
    run(cmd)
    source.unlink()
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_launcher(app: Path, app_support: Path, *, portable_launcher: bool = False) -> None:
    macos_dir = app / "Contents" / "MacOS"
    launcher = macos_dir / TARGET_EXECUTABLE_NAME
    real = macos_dir / f"{TARGET_EXECUTABLE_NAME}.real"
    source_executable = macos_dir / TARGET_EXECUTABLE_NAME
    if not source_executable.exists():
        source_executable = macos_dir / UPSTREAM_EXECUTABLE_NAME

    if real.exists():
        real.unlink()
    if not source_executable.exists():
        raise SystemExit(f"source executable not found in staged app: {source_executable}")
    source_executable.rename(real)

    default_datadir = (
        "~/Library/Application Support/OrcaSlicer-Codex"
        if portable_launcher
        else str(app_support)
    )

    write_native_launcher(launcher, real, default_datadir)


def preserve_existing_identity_assets(existing_app: Path, staged_app: Path) -> None:
    copy_optional_file(
        existing_app / "Contents" / "Resources" / "Icon.icns",
        staged_app / "Contents" / "Resources" / "Icon.icns",
    )


def main() -> int:
    source_root, built_app = repo_defaults()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=source_root)
    parser.add_argument("--source-app", type=Path, default=built_app)
    parser.add_argument("--target-app", type=Path, default=DEFAULT_TARGET_APP)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--stage-dir", type=Path, default=Path("/tmp/TinManX1-install-stage"))
    parser.add_argument("--portable-launcher", action="store_true")
    parser.add_argument("--allow-debug-source", action="store_true")
    parser.add_argument("--skip-auto-pa-profile-hook", action="store_true")
    parser.add_argument("--skip-codesign", action="store_true")
    args = parser.parse_args()

    if not args.source_app.exists():
        raise SystemExit(f"source app not found: {args.source_app}")
    source_config = source_build_configuration(args.source_app)
    if source_config == "Debug" and not args.allow_debug_source:
        raise SystemExit(
            "refusing to install a Debug app bundle; use a Release or RelWithDebInfo build "
            "(pass --allow-debug-source only for an intentional local diagnostic install)"
        )
    if args.target_app.name != f"{EXPECTED_TARGET_NAME}.app":
        raise SystemExit(f"refusing unexpected target app path: {args.target_app}")

    staged_app = args.stage_dir / args.target_app.name
    if staged_app.exists():
        shutil.rmtree(staged_app)
    args.stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        args.source_app,
        staged_app,
        symlinks=False,
        ignore=shutil.ignore_patterns(*GENERATED_RESOURCE_PATTERNS),
    )

    if args.target_app.exists():
        preserve_existing_identity_assets(args.target_app, staged_app)

    version = update_info_plist(staged_app)
    write_launcher(staged_app, args.app_support, portable_launcher=args.portable_launcher)
    install_feature_resources(args.source_root, staged_app)

    if not args.skip_codesign:
        run(["codesign", "--force", "--deep", "--sign", "-", str(staged_app)])

    backup_path = None
    if args.target_app.exists():
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = args.target_app.with_name(f"{args.target_app.name}.backup-{timestamp}")
        args.target_app.rename(backup_path)

    try:
        shutil.move(str(staged_app), str(args.target_app))
        run(["xattr", "-dr", "com.apple.quarantine", str(args.target_app)])
    except Exception:
        if args.target_app.exists():
            shutil.rmtree(args.target_app)
        if backup_path and backup_path.exists():
            backup_path.rename(args.target_app)
        raise

    if not args.skip_auto_pa_profile_hook:
        try:
            install_auto_pa_profile_hook(args.source_root, args.target_app, args.app_support)
        except SystemExit as exc:
            print(f"Warning: TinMan auto-PA profile hook failed with exit code {exc.code}", file=sys.stderr)

    archived_preflight = archive_legacy_launch_preflight(args.app_support)

    print(f"Installed {args.target_app}")
    print(f"Source {args.source_app}")
    print(f"Version {version}")
    if backup_path:
        print(f"Backup {backup_path}")
    if archived_preflight:
        print(f"Archived legacy launch preflight {archived_preflight}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
