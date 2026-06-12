import { SEO_LANDING_PATHS } from '../content/seo/catalog.js'

/**
 * @param {string} siteUrl
 * @returns {{ robots: string, sitemap: string, ogImage: string, security: string }}
 */
export function buildSeoAssets(siteUrl) {
  const base = siteUrl.replace(/\/$/, '')
  const ogImage = `${base}/icons/podorozhnik-logo.png`

  const seoSitemapEntries = SEO_LANDING_PATHS.map(
    (path) => `  <url>
    <loc>${base}${path}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>`,
  ).join('\n')

  const robots = `User-agent: *
Allow: /

# Закрытые разделы SPA
Disallow: /cabinet
Disallow: /admin

Sitemap: ${base}/sitemap.xml
`

  const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${base}/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>${base}/login</loc>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
  <url>
    <loc>${base}/register</loc>
    <changefreq>monthly</changefreq>
    <priority>0.4</priority>
  </url>
  <url>
    <loc>${base}/terms</loc>
    <changefreq>yearly</changefreq>
    <priority>0.2</priority>
  </url>
  <url>
    <loc>${base}/privacy</loc>
    <changefreq>yearly</changefreq>
    <priority>0.2</priority>
  </url>
  <url>
    <loc>${base}/consent</loc>
    <changefreq>yearly</changefreq>
    <priority>0.1</priority>
  </url>
  <url>
    <loc>${base}/refund</loc>
    <changefreq>yearly</changefreq>
    <priority>0.1</priority>
  </url>
  <url>
    <loc>${base}/cookies</loc>
    <changefreq>yearly</changefreq>
    <priority>0.1</priority>
  </url>
  <url>
    <loc>${base}/marketing</loc>
    <changefreq>yearly</changefreq>
    <priority>0.1</priority>
  </url>
${seoSitemapEntries}
</urlset>
`

  const security = `# security.txt (RFC 9116) — укажите рабочий mailto
Contact: mailto:security@example.com
Preferred-Languages: ru, en
Canonical: ${base}/.well-known/security.txt
`

  return { robots, sitemap, ogImage, security }
}
