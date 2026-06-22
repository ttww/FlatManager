/**
 * Generate guest UI screenshots in all supported languages.
 * 
 * Prerequisites:
 * - Guest UI must be running on http://localhost:5173
 * - npm packages: playwright
 * 
 * Usage:
 *   cd docs
 *   node generate-guest-screenshots.js
 */

import * as fs from "fs";
import * as path from "path";
import { chromium } from "playwright";

const screenshotsDir = "./screenshots";

type Locale =
  | "ar"
  | "cs"
  | "de"
  | "el"
  | "en"
  | "eo"
  | "es"
  | "fr"
  | "he"
  | "hi"
  | "hu"
  | "ja"
  | "ko"
  | "pl"
  | "pt"
  | "ru"
  | "uk"
  | "zh";

const LANGUAGES: Locale[] = [
  "en",
  "de",
  "cs",
  "uk",
  "ru",
  "ja",
  "zh",
  "ko",
  "ar",
  "fr",
  "es",
  "pt",
  "pl",
  "hu",
  "eo",
  "hi",
  "el",
  "he",
];

const LANGUAGE_NAMES: Record<Locale, string> = {
  en: "English",
  de: "Deutsch",
  cs: "Čeština",
  uk: "Українська",
  ru: "Русский",
  ja: "日本語",
  zh: "中文",
  ko: "한국어",
  ar: "العربية",
  fr: "Français",
  es: "Español",
  pt: "Português",
  pl: "Polski",
  hu: "Magyar",
  eo: "Esperanto",
  hi: "हिन्दी",
  el: "Ελληνικά",
  he: "עברית",
};

async function generateScreenshots() {
  // Ensure screenshots directory exists
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  const browser = await chromium.launch();

  try {
    for (const locale of LANGUAGES) {
      console.log(`📸 Capturing ${LANGUAGE_NAMES[locale]} (${locale})...`);

      const page = await browser.newPage({
        viewport: { width: 1440, height: 900 },
      });

      try {
        // Navigate to guest page
        await page.goto("http://localhost:5173/", {
          waitUntil: "networkidle",
        });

        // Wait for language selector
        await page.waitForSelector('select#locale', {
          timeout: 5000,
        });

        // Select the language from dropdown
        await page.selectOption('select#locale', locale);

        // Wait for content to update (small delay for re-render)
        await page.waitForTimeout(500);

        // Take screenshot
        const filename = `guest-${locale}.png`;
        const filepath = path.join(screenshotsDir, filename);
        await page.screenshot({
          path: filepath,
          fullPage: false,
        });

        console.log(`  ✅ Saved: ${filename}`);
      } finally {
        await page.close();
      }
    }

    console.log(`\n✨ All ${LANGUAGES.length} screenshots generated successfully!`);
  } finally {
    await browser.close();
  }
}

generateScreenshots().catch((err) => {
  console.error("Error generating screenshots:", err);
  process.exit(1);
});
