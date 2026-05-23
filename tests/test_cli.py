from typer.testing import CliRunner

from foodanalyzer.cli import app


runner = CliRunner()


def test_cli_analyze_offline_happy_path():
    result = runner.invoke(
        app,
        ["analyze", "data/rice_chicken_broccoli.png", "--offline"],
    )
    assert result.exit_code == 0
    assert "TOTAL" in result.output
    assert "broccoli" in result.output


def test_cli_analyze_offline_unknown_meal():
    result = runner.invoke(
        app,
        ["analyze", "data/no_meal_blue.png", "--offline"],
    )
    assert result.exit_code == 0
    assert "No meal was recognized" in result.output


def test_cli_rejects_missing_image():
    result = runner.invoke(app, ["analyze", "data/missing.png", "--offline"])
    assert result.exit_code == 2
    assert "Invalid image" in result.output
