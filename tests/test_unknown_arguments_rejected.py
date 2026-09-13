"""An unrecognised tool argument must be an error, never a silent default (#10).

The defect this guards was not a typo's problem. `github_merge_pr` was called
with `merge_method="merge"`; the real parameter is `method`, the unknown key was
dropped by the SDK's own argument validation, and the call squash-merged a pull
request and deleted its branch while reporting `success: true` and
`"method": "squash"`. Minutes later the same hole filed an issue in the wrong
repository, because `repo` is spelled `repo_path`.

So these tests assert the property on the REAL registered tools rather than on a
sample function: the point is that this server's mutating surface rejects what it
does not recognise, and a test against a toy signature would pass while the
server stayed lenient.

ASCII only, Windows-safe.
"""

import pydantic
import pytest

import server


@pytest.fixture(scope="module", autouse=True)
def hardened():
    """Apply the hardening once, as the server's __main__ block does."""
    count = server._forbid_unknown_arguments()
    assert count > 0, "no tool argument model was hardened"
    return count


def _arg_model(tool_name: str):
    return server.mcp._tool_manager._tools[tool_name].fn_metadata.arg_model


class TestTheMisrouteThatCausedThis:
    def test_merge_pr_rejects_the_misspelled_merge_method(self):
        """The exact call that squash-merged a PR asking for a merge commit."""
        with pytest.raises(pydantic.ValidationError) as caught:
            _arg_model("github_merge_pr").model_validate(
                {"number": 25, "merge_method": "merge"}
            )
        assert "merge_method" in str(caught.value)

    def test_create_issue_rejects_the_misspelled_repo(self):
        """The second misroute: `repo` instead of `repo_path` filed an issue in
        the default repository."""
        with pytest.raises(pydantic.ValidationError) as caught:
            _arg_model("github_create_issue").model_validate(
                {"title": "t", "repo": "techdeveloper-org/mcp-github-api"}
            )
        assert "repo" in str(caught.value)

    def test_the_correct_spelling_still_works(self):
        """A guard that rejects valid input is worse than the defect."""
        parsed = _arg_model("github_merge_pr").model_validate(
            {"number": 25, "method": "merge"}
        )
        assert parsed.model_dump_one_level()["method"] == "merge"


class TestEveryToolNotJustTheTwoThatBit:
    def test_all_registered_tools_forbid_extras(self):
        """Named individually in the failure message, because "some tool is
        lenient" is not actionable."""
        lenient = [
            name
            for name, tool in server.mcp._tool_manager._tools.items()
            if tool.fn_metadata.arg_model.model_config.get("extra") != "forbid"
        ]
        assert lenient == [], f"tools still accepting unknown arguments: {lenient}"


class TestTheGuardDegradesRatherThanBreaks:
    def test_a_moved_registry_warns_and_does_not_raise(self, monkeypatch, capsys):
        """This reads SDK internals. A layout change under either mcp major
        version must cost a warning, not the whole server: running with lenient
        validation beats not running, provided the log says which it is."""
        monkeypatch.setattr(server.mcp, "_tool_manager", object(), raising=False)
        assert server._forbid_unknown_arguments() == 0
        assert "WARNING" in capsys.readouterr().err
