import pytest
import typer

from pytodo.cli import prompt
from pytodo.cli.main import handle_errors


@pytest.mark.parametrize("code", [0, 1, 2])
def test_handle_errors_lets_clean_exits_through(code):
    # typer.Exit subclasses RuntimeError, so a naive `except RuntimeError`
    # swallows every clean exit and turns it into a failure whose message is
    # the exit code. Guard the re-raise.
    @handle_errors
    def command():
        raise typer.Exit(code)

    with pytest.raises(typer.Exit) as excinfo:
        command()
    assert excinfo.value.exit_code == code


def test_handle_errors_still_traps_runtime_error():
    @handle_errors
    def command():
        raise RuntimeError("boom")

    with pytest.raises(typer.Exit) as excinfo:
        command()
    assert excinfo.value.exit_code == 2


def test_handle_errors_maps_cancelled_to_exit_1():
    @handle_errors
    def command():
        raise prompt.Cancelled()

    with pytest.raises(typer.Exit) as excinfo:
        command()
    assert excinfo.value.exit_code == 1


def test_handle_errors_maps_missing_tool_to_exit_2():
    @handle_errors
    def command():
        raise prompt.MissingTool("fzf is required")

    with pytest.raises(typer.Exit) as excinfo:
        command()
    assert excinfo.value.exit_code == 2
