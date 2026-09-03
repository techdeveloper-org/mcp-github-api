"""Unit tests for github_validate_build's "no build system detected" case.

Regression coverage for a defect where a repo with no recognized build
manifest at its root (package.json / pom.xml / build.gradle / requirements.txt
or setup.py / Cargo.toml) -- e.g. a monorepo with backend/requirements.txt and
frontend/package.json but nothing at root -- returned validated=False, which
github_full_merge_cycle's `if not build_result.get("validated")` check then
read as "the build failed", unconditionally blocking every merge through that
tool for any project shaped this way. "No build system to check" and "build
system found but failed" are different outcomes and must not collapse into
the same validated=False result.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import github_validate_build  # noqa: E402


def _validate(repo_path):
    raw = github_validate_build(repo_path=str(repo_path))
    return json.loads(raw) if isinstance(raw, str) else raw


class TestNoBuildSystemDoesNotBlockMerge:
    def test_empty_repo_root_reports_validated_true(self, tmp_path):
        result = _validate(tmp_path)

        assert result["build_system"] == "unknown"
        assert result["validated"] is True, (
            "no build manifest at root must not read as a failed build -- "
            f"got: {result}"
        )
        assert result.get("skipped") is True

    def test_monorepo_with_only_subdirectory_manifests_reports_validated_true(self, tmp_path):
        (tmp_path / "backend").mkdir()
        (tmp_path / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        (tmp_path / "frontend").mkdir()
        (tmp_path / "frontend" / "package.json").write_text("{}\n", encoding="utf-8")

        result = _validate(tmp_path)

        assert result["build_system"] == "unknown"
        assert result["validated"] is True, (
            f"subdirectory-only manifests must not block a root-level merge check: {result}"
        )
