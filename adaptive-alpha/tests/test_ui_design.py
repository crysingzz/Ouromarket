from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "adaptive_alpha" / "ui"


def test_compact_accessible_navigation_contract() -> None:
    page = (ROOT / "index.html").read_text()
    assert '<meta name="theme-color" content="#000000">' in page
    assert "Ouromarket · Operator workspace" in page
    assert '<span class="brand-mark">&gt;&gt;</span>' in page
    assert page.count('class="nav-item') == 7
    for name in (
        "Overview",
        "Research lab",
        "Autonomous R&amp;D",
        "Strategy registry",
        "Portfolio &amp; execution",
        "Risk controls",
        "Audit trail",
    ):
        assert f'aria-label="{name}"' in page


def test_monochrome_responsive_theme_is_local() -> None:
    styles = (ROOT / "styles.css").read_text()
    assert "--canvas: #000" in styles
    assert "--rail-width: 92px" in styles
    assert "grid-template-columns: repeat(7,minmax(0,1fr))" in styles
    assert "inset: auto 0 0" in styles
    assert "prefers-reduced-motion: reduce" in styles
    assert "outline: 2px solid var(--paper)" in styles
    assert "http://" not in styles and "https://" not in styles
    assert styles.count("@import") == 1
    assert "url('/assets/fonts.css')" in styles
