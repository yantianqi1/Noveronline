from pathlib import Path


FORBIDDEN_MARKERS = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL_NAME",
)
TEXT_SUFFIXES = {".py", ".js", ".vue", ".md", ".txt", ".json", ".example"}


def test_runtime_surfaces_do_not_reference_legacy_llm_env_vars():
    repo_root = Path(__file__).resolve().parents[2]
    targets = [
        repo_root / "backend" / "app",
        repo_root / "frontend" / "src",
        repo_root / "README.md",
        repo_root / ".env.example",
        repo_root / "docs" / "CODEX_HANDOFF_GUIDE.md",
    ]

    violations = []
    for target in targets:
        files = target.rglob("*") if target.is_dir() else [target]
        for path in files:
            if path.is_dir():
                continue
            if path.suffix not in TEXT_SUFFIXES and path.name != ".env.example":
                continue
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_MARKERS:
                if marker in text:
                    violations.append(f"{path.relative_to(repo_root)} -> {marker}")

    assert violations == []
