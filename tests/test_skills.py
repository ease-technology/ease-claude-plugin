"""Every skill's SKILL.md has frontmatter the plugin loader can read."""
import pathlib

SKILLS = pathlib.Path(__file__).parent.parent / "skills"


def frontmatter(path):
    """The lines between the opening and closing `---` of a SKILL.md."""
    lines = path.read_text().splitlines()
    assert lines and lines[0] == "---", f"{path} does not start with ---"
    assert "---" in lines[1:], f"{path} has no closing ---"
    return lines[1 : lines.index("---", 1)]


def field(lines, key):
    """The value of the `key:` line, or None when there is none."""
    for line in lines:
        if line.startswith(f"{key}:"):
            return line[len(key) + 1 :].strip()
    return None


def test_every_skill_has_name_and_description():
    paths = sorted(SKILLS.glob("*/SKILL.md"))
    assert paths, "no skills found"
    for path in paths:
        lines = frontmatter(path)
        assert field(lines, "name") == path.parent.name, path
        assert field(lines, "description"), f"{path} has an empty description"


def test_autopilot_skill_names_its_rules():
    text = (SKILLS / "autopilot" / "SKILL.md").read_text()
    for term in ("jev-opinion", "--by autopilot", "ASK JUAN"):
        assert term in text, term
