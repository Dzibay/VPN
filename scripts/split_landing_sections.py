# -*- coding: utf-8 -*-
"""One-off: split HomeView.vue into section template files."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "frontend" / "src"
home = root / "views" / "HomeView.vue"
lines = home.read_text(encoding="utf-8").splitlines()

markers = [
    ("HomeHeroSection", 473, 599),
    ("LandingWhySection", 599, 629),
    ("LandingHowSection", 629, 856),
    ("LandingTrialSection", 856, 985),
    ("LandingPricingSection", 985, 1182),
    ("LandingFaqSection", 1182, 1314),
    ("LandingFinalCtaSection", 1314, 1414),
    ("LandingFooter", 1414, 1596),
]

landing = root / "components" / "landing"
landing.mkdir(parents=True, exist_ok=True)

styles = "\n".join(lines[1597:4483])
(root / "styles" / "landing-page.css").write_text(styles, encoding="utf-8")

for name, start, end in markers:
    template = "\n".join(lines[start - 1 : end - 1])
    (landing / f"{name}.template.html").write_text(template, encoding="utf-8")
    print(name, "lines", end - start)

print("css bytes", len(styles.encode("utf-8")))
