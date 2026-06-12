# -*- coding: utf-8 -*-
"""Generate landing section .vue files from extracted templates."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "frontend" / "src"
landing = root / "components" / "landing"

CTX = """const {
  HOME_IMAGES,
  ArrowRight,
  Building2,
  CheckCircle2,
  Gauge,
  Clock,
  Gift,
  Globe,
  Headphones,
  HelpCircle,
  Lock,
  MapPin,
  MessageCircle,
  Monitor,
  RefreshCw,
  Rocket,
  Route,
  Send,
  Shield,
  ShieldCheck,
  Smartphone,
  Star,
  Wifi,
  Zap,
  LEGAL_FOOTER_LINKS,
  footerHighlights,
  footerPayBrands,
  heroMiniFeatures,
  whyChooseFeatures,
  howVpnApps,
  howDirectApps,
  howVpnPerks,
  howDirectPerks,
  howHighlights,
  trialFeatures,
  trialVisualOrbit,
  planIncludes,
  pricingTrustTop,
  pricingBenefitsBottom,
  pricingLoading,
  plans,
  faqs,
  activeFaq,
  toggleFaq,
  faqTrustHighlights,
  supportTelegramUrl,
  supportTelegramLabel,
  footerProductLinks,
  finalCtaFeatures,
  finalVisualPins,
  isLoggedIn,
  loggedInHomeCtaPath,
} = useLandingPageContext()
"""

sections = {
    "HomeHeroSection": ["AppActionButton"],
    "LandingWhySection": [],
    "LandingHowSection": [],
    "LandingTrialSection": ["RouterLink"],
    "LandingPricingSection": ["RouterLink"],
    "LandingFaqSection": [],
    "LandingFinalCtaSection": ["RouterLink"],
    "LandingFooter": [],
}

for name, extra_imports in sections.items():
    template = (landing / f"{name}.template.html").read_text(encoding="utf-8")
    imports = [
        "import { useLandingPageContext } from '../../composables/useLandingPage.js'",
    ]
    if "AppActionButton" in extra_imports:
        imports.append("import AppActionButton from '../AppActionButton.vue'")
    if "RouterLink" in extra_imports:
        imports.append("import { RouterLink } from 'vue-router'")

    script = "<script setup>\n" + "\n".join(imports) + "\n\n" + CTX + "\n</script>\n\n"
    (landing / f"{name}.vue").write_text(script + "<template>\n" + template + "\n</template>\n", encoding="utf-8")
    print("wrote", name)

# LandingPageMain wrapper
main = '''<script setup>
import LandingWhySection from './LandingWhySection.vue'
import LandingHowSection from './LandingHowSection.vue'
import LandingTrialSection from './LandingTrialSection.vue'
import LandingPricingSection from './LandingPricingSection.vue'
import LandingFaqSection from './LandingFaqSection.vue'
import LandingFinalCtaSection from './LandingFinalCtaSection.vue'
</script>

<template>
  <LandingWhySection />
  <LandingHowSection />
  <LandingTrialSection />
  <LandingPricingSection />
  <LandingFaqSection />
  <LandingFinalCtaSection />
  <slot />
</template>
'''
(landing / "LandingPageMain.vue").write_text(main, encoding="utf-8")
print("wrote LandingPageMain")
