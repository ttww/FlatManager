/**
 * Generate all FlatManager UI screenshots:
 * - Admin UI (6 pages)
 * - Guest UI flow (3 states)
 * - Guest UI languages (18 languages)
 *
 * Prerequisites:
 * - Reachable deployment at https://experiments.thomaswelsch.de
 * - npm packages: playwright
 *
 * Usage:
 *   cd docs
 *   npm run screenshots
 */
import * as fs from "fs";
import * as path from "path";
import { chromium } from "playwright";
const screenshotsDir = "./screenshots";
const VIEWPORT = { width: 1440, height: 900 };
const ADMIN_TOKEN = "299726ac7b0c3c67bf4d61f64e89021a8fa714877e02236a3fbeebb574c61099";
const ORIGIN = "https://experiments.thomaswelsch.de";
const ADMIN_BASE_URL = `${ORIGIN}/admin`;
const GUEST_BASE_URL = `${ORIGIN}/guest`;
const LANGUAGES = [
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
const LANGUAGE_NAMES = {
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
async function ensureDirectory() {
    if (!fs.existsSync(screenshotsDir)) {
        fs.mkdirSync(screenshotsDir, { recursive: true });
    }
}
async function takeScreenshot(page, filename, description) {
    try {
        const filepath = path.join(screenshotsDir, filename);
        await page.screenshot({
            path: filepath,
            fullPage: false,
        });
        console.log(`  ✅ ${description}`);
        return true;
    }
    catch (err) {
        console.error(`  ❌ ${description}: ${err}`);
        return false;
    }
}
async function generateAdminScreenshots(browser) {
    console.log("\n📸 Generating Admin UI Screenshots...\n");
    const page = await browser.newPage({ viewport: VIEWPORT });
    try {
        // 1. Login page
        console.log("Capturing admin-01-login.png...");
        await page.goto(`${ADMIN_BASE_URL}/login`, { waitUntil: "networkidle" });
        await page.waitForSelector("#token", { timeout: 10000 });
        await takeScreenshot(page, "admin-01-login.png", "Login page");
        // Store token in localStorage
        await page.evaluate((token) => {
            localStorage.setItem("flatmanager.adminToken", token);
        }, ADMIN_TOKEN);
        // 2-6. Navigate to each admin page and take screenshot
        const adminPages = [
            { path: "/codes", filename: "admin-02-codes.png", name: "Codes" },
            { path: "/devices", filename: "admin-03-devices.png", name: "Devices" },
            { path: "/commands", filename: "admin-04-commands.png", name: "Commands" },
            { path: "/logs", filename: "admin-05-logs.png", name: "Logs" },
            { path: "/support", filename: "admin-06-support.png", name: "Support" },
        ];
        for (const { path: pagePath, filename, name } of adminPages) {
            console.log(`Capturing ${filename}...`);
            await page.goto(`${ADMIN_BASE_URL}${pagePath}`, { waitUntil: "networkidle" });
            // Wait for content to load
            await page.waitForTimeout(1500);
            const isOnLogin = /\/admin\/login/.test(page.url());
            if (isOnLogin) {
                throw new Error(`Unexpected redirect to login while capturing ${filename}`);
            }
            await takeScreenshot(page, filename, `${name} page`);
        }
        console.log("\n✨ Admin UI screenshots complete!");
    }
    finally {
        await page.close();
    }
}
async function fillAndSubmitGuestForm(page, apartmentId, code) {
    await page.fill("#apartment", apartmentId);
    await page.fill("#code", code);
    await page.click("button.cta");
}
async function generateGuestFlowScreenshots(browser) {
    console.log("\n📸 Generating Guest UI Flow Screenshots...\n");
    // 1. Open form (idle state)
    console.log("Capturing guest-01-open-form.png...");
    const page1 = await browser.newPage({ viewport: VIEWPORT });
    try {
        await page1.goto(`${GUEST_BASE_URL}/`, { waitUntil: "networkidle" });
        await page1.waitForSelector("#apartment", { timeout: 10000 });
        await page1.waitForSelector("#code", { timeout: 10000 });
        await takeScreenshot(page1, "guest-01-open-form.png", "Open form (idle state)");
    }
    finally {
        await page1.close();
    }
    // 2. Success state (door-opened)
    console.log("Capturing guest-02-success.png...");
    const page2 = await browser.newPage({ viewport: VIEWPORT });
    try {
        let statusPollCount = 0;
        await page2.route("**/api/guest/open", async (route) => {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    status: "accepted",
                    message: "accepted",
                    command_id: 9001,
                }),
            });
        });
        await page2.route("**/api/guest/command-status/**", async (route) => {
            statusPollCount += 1;
            const status = statusPollCount < 2 ? "delivered" : "done";
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({ status }),
            });
        });
        await page2.goto(`${GUEST_BASE_URL}/`, { waitUntil: "networkidle" });
        await page2.waitForSelector("#apartment", { timeout: 10000 });
        await fillAndSubmitGuestForm(page2, "A-101", "123456");
        await page2.waitForSelector(".status-panel.door-opened", { timeout: 12000 });
        await takeScreenshot(page2, "guest-02-success.png", "Success state (door opened)");
    }
    finally {
        await page2.close();
    }
    // 3. Denied state
    console.log("Capturing guest-03-denied.png...");
    const page3 = await browser.newPage({ viewport: VIEWPORT });
    try {
        await page3.route("**/api/guest/open", async (route) => {
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    status: "denied",
                    message: "denied",
                    command_id: null,
                }),
            });
        });
        await page3.goto(`${GUEST_BASE_URL}/`, { waitUntil: "networkidle" });
        await page3.waitForSelector("#apartment", { timeout: 10000 });
        await fillAndSubmitGuestForm(page3, "A-101", "111111");
        await page3.waitForSelector(".status-panel.denied", { timeout: 12000 });
        await takeScreenshot(page3, "guest-03-denied.png", "Denied state");
    }
    finally {
        await page3.close();
    }
    console.log("\n✨ Guest UI flow screenshots complete!");
}
async function generateQrScreenshot(browser) {
    console.log("\n📸 Generating QR Code Screenshot...\n");
    const DUMMY_APARTMENT = "apartment-101";
    const DUMMY_URL = `https://example.com/guest/?apartment_id=${DUMMY_APARTMENT}`;
    const page = await browser.newPage({ viewport: VIEWPORT });
    try {
        // Inject auth token before navigation
        await page.goto(`${ADMIN_BASE_URL}/login`, { waitUntil: "networkidle" });
        await page.evaluate((token) => {
            localStorage.setItem("flatmanager.adminToken", token);
        }, ADMIN_TOKEN);
        // Mock all admin API calls so the page renders instantly with our dummy apartment
        await page.route("**/api/admin/apartments**", (route) => route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([
                { apartment_id: DUMMY_APARTMENT, timezone: "Europe/Berlin" },
            ]),
        }));
        await page.route("**/api/admin/devices**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
        await page.route("**/api/admin/access-codes**", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
        console.log("Capturing admin-07-qr-modal.png...");
        await page.goto(`${ADMIN_BASE_URL}/apartments`, { waitUntil: "networkidle" });
        await page.waitForTimeout(1000);
        // Click the QR Code button for the dummy apartment row
        const qrButton = page.getByRole("button", { name: "QR Code" }).first();
        await qrButton.waitFor({ timeout: 8000 });
        await qrButton.click();
        // Wait for the modal canvas (QR code rendered) to appear
        await page.waitForSelector(".modal-backdrop canvas", { timeout: 8000 });
        await page.waitForTimeout(400); // let qrcode.js finish drawing
        // Overwrite the URL displayed in the modal with the dummy URL
        await page.evaluate((url) => {
            const p = document.querySelector(".modal-url");
            if (p)
                p.textContent = url;
        }, DUMMY_URL);
        await takeScreenshot(page, "admin-07-qr-modal.png", "QR Code modal");
        console.log("\n✨ QR Code screenshot complete!");
    }
    finally {
        await page.close();
    }
}
async function generateGuestLanguageScreenshots(browser) {
    console.log("\n📸 Generating Guest UI Language Screenshots...\n");
    let successCount = 0;
    for (const locale of LANGUAGES) {
        console.log(`Capturing guest-${locale}.png (${LANGUAGE_NAMES[locale]})...`);
        const page = await browser.newPage({ viewport: VIEWPORT });
        try {
            await page.goto(`${GUEST_BASE_URL}/`, { waitUntil: "networkidle" });
            // Wait for language selector
            await page.waitForSelector("select#locale", { timeout: 10000 });
            // Select the language from dropdown
            await page.selectOption("select#locale", locale);
            // Wait for content to update
            await page.waitForTimeout(500);
            const success = await takeScreenshot(page, `guest-${locale}.png`, `${LANGUAGE_NAMES[locale]} form`);
            if (success)
                successCount++;
        }
        finally {
            await page.close();
        }
    }
    console.log(`\n✨ Guest UI language screenshots complete! (${successCount}/${LANGUAGES.length})`);
}
async function main() {
    console.log("🚀 FlatManager Screenshot Generator\n");
    await ensureDirectory();
    const browser = await chromium.launch();
    try {
        // Generate all screenshot categories
        await generateAdminScreenshots(browser);
        await generateQrScreenshot(browser);
        await generateGuestFlowScreenshots(browser);
        await generateGuestLanguageScreenshots(browser);
        console.log("\n✨ All screenshots generated successfully!");
    }
    catch (err) {
        console.error("Error generating screenshots:", err);
        process.exit(1);
    }
    finally {
        await browser.close();
    }
}
main();
