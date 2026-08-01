"""
Execute the documentation and check that it says what the code does.

Every ```python block in docs/ is run, in order, in one namespace per page —
so a page reads as a session, and a later block can use what an earlier one
defined.  When a python block is immediately followed by a ```text block, that
text is treated as the expected stdout and compared exactly.

This is the same idea as a doctest, applied to the tutorials.  It exists
because prose goes stale silently: the `>>>` example in `card/__init__.py`
advertised a Flood secular age of 537313592 for years after the closed-form
integral changed the answer to 533337567, and nothing failed, because nothing
ran it.

Blocks in any other language (```bash, ```yaml, ```text on its own) are not
executed.  A python block that should be shown but not run can be marked with
a `# docs: skip` comment on its first line.

Each page runs in a subprocess with a scratch working directory, so pages
cannot interfere with each other and the figures they write land in the
temporary directory rather than the repo.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

#: Separator printed between blocks so the outputs can be split apart again.
#: Deliberately unlikely to appear in any real output.
BLOCK_SEPARATOR = "<<<card-docs-block-boundary>>>"

FENCE = re.compile(
    r"^```(?P<language>[a-zA-Z]*)[^\n]*\n(?P<body>.*?)^```",
    re.MULTILINE | re.DOTALL,
)


def markdown_pages():
    """Every documentation page, excluding the Quarto paper's directory."""
    return sorted(
        path for path in DOCS_DIR.rglob("*.md")
        if "paper" not in path.relative_to(DOCS_DIR).parts
    )


def parse_blocks(text):
    """[(language, body), ...] for every fenced block on a page, in order."""
    return [(match.group("language").lower(), match.group("body"))
            for match in FENCE.finditer(text)]


def executable_blocks(text):
    """
    [(code, expected_stdout_or_None), ...] for the runnable blocks of a page.

    A ```text block immediately after a ```python block is that block's
    expected output.
    """
    blocks = parse_blocks(text)
    out = []
    for i, (language, body) in enumerate(blocks):
        if language != "python" or body.lstrip().startswith("# docs: skip"):
            continue
        expected = None
        if i + 1 < len(blocks) and blocks[i + 1][0] == "text":
            expected = blocks[i + 1][1]
        out.append((body, expected))
    return out


def run_page(blocks, workdir):
    """Run a page's code blocks in one subprocess; return per-block stdout."""
    script = f"\nprint({BLOCK_SEPARATOR!r})\n".join(code for code, _ in blocks)
    environment = dict(os.environ, MPLBACKEND="Agg")
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=workdir, env=environment,
    )
    assert result.returncode == 0, (
        f"a documentation example raised:\n{result.stderr}"
    )
    return result.stdout.split(BLOCK_SEPARATOR)


@pytest.mark.parametrize("page", markdown_pages(), ids=lambda p: p.name)
def test_documentation_examples_run_and_print_what_they_claim(page, tmp_path):
    blocks = executable_blocks(page.read_text())
    if not blocks:
        pytest.skip("no executable examples on this page")

    outputs = run_page(blocks, tmp_path)
    assert len(outputs) == len(blocks)

    for index, ((code, expected), actual) in enumerate(zip(blocks, outputs)):
        if expected is None:
            continue
        first_line = code.strip().splitlines()[0]
        assert actual.strip() == expected.strip(), (
            f"{page.name}: block {index + 1} (starting `{first_line}`) printed\n"
            f"---- actual ----\n{actual.strip()}\n"
            f"---- documented ----\n{expected.strip()}\n"
        )


def test_every_page_is_in_the_nav():
    """A page missing from mkdocs.yml is invisible on the site, and mkdocs
    only warns about it in strict mode."""
    nav = (DOCS_DIR.parent / "mkdocs.yml").read_text()
    for page in markdown_pages():
        relative = page.relative_to(DOCS_DIR).as_posix()
        assert relative in nav, f"{relative} is not listed in mkdocs.yml nav"


def test_the_config_shown_in_the_docs_is_the_one_that_ships():
    """docs/cli.md prints a complete run config and says `card init` writes
    exactly this.  Compare the parsed contents, not the text, so comments and
    formatting can differ but no setting can."""
    import yaml

    from card.config import example_config_text

    blocks = [body for language, body
              in parse_blocks((DOCS_DIR / "cli.md").read_text())
              if language == "yaml"]
    assert blocks, "docs/cli.md no longer shows a config"

    assert yaml.safe_load(blocks[0]) == yaml.safe_load(example_config_text())


def test_api_pages_cover_every_public_module():
    """Each module of the package needs a page, or its API is undocumented."""
    package = DOCS_DIR.parent / "src" / "card"
    modules = {
        path.stem for path in package.glob("*.py")
        if not path.stem.startswith("_")
        # The deprecation shims re-export other modules and are not documented.
        and path.stem not in {"decay_solver", "card_mcmc", "create_custom_plots"}
    }
    documented = {path.stem for path in (DOCS_DIR / "api").glob("*.md")}
    assert modules - documented == set(), (
        f"undocumented module(s): {sorted(modules - documented)}"
    )
