/**
 * Baileys WhatsApp API Server
 * Fast WA number checker for Earning Hub Bot
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const express = require("express");
const pino = require("pino");
const qrcode = require("qrcode");
const fs = require("fs");

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const AUTH_DIR = process.env.AUTH_DIR || "./wa_auth";

// ── State ──────────────────────────────────────────────
let sock = null;
let isConnected = false;
let currentQR = null;
let isReconnecting = false;

// ── Connect ────────────────────────────────────────────
async function connectWA() {
  if (isReconnecting) return;
  isReconnecting = true;

  try {
    if (!fs.existsSync(AUTH_DIR)) fs.mkdirSync(AUTH_DIR, { recursive: true });

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
      version,
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, pino({ level: "silent" })),
      },
      logger: pino({ level: "silent" }),
      printQRInTerminal: true,
      browser: ["Ubuntu", "Chrome", "22.04.4"],
      generateHighQualityLinkPreview: false,
      syncFullHistory: false,
      markOnlineOnConnect: false,
      connectTimeoutMs: 30000,
      defaultQueryTimeoutMs: 20000,
    });

    sock.ev.on("connection.update", async ({ connection, lastDisconnect, qr }) => {
      if (qr) {
        currentQR = qr;
        isConnected = false;
        console.log("📱 QR Code ready — scan করো");
      }

      if (connection === "open") {
        isConnected = true;
        currentQR = null;
        isReconnecting = false;
        console.log("✅ WhatsApp Connected!");
      }

      if (connection === "close") {
        isConnected = false;
        isReconnecting = false;
        const code = lastDisconnect?.error?.output?.statusCode;
        const loggedOut = code === DisconnectReason.loggedOut || code === 401;
        console.log(`❌ Disconnected (code: ${code}). LoggedOut: ${loggedOut}`);

        if (!loggedOut) {
          console.log("🔄 5 সেকেন্ড পর reconnect হবে...");
          setTimeout(connectWA, 5000);
        } else {
          console.log("🚫 Logged out — auth delete করো এবং restart করো");
          // Auth clear করে reconnect
          try {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
          } catch {}
          setTimeout(connectWA, 3000);
        }
      }
    });

    sock.ev.on("creds.update", saveCreds);
  } catch (e) {
    console.error("connectWA error:", e.message);
    isReconnecting = false;
    setTimeout(connectWA, 10000);
  }
}

connectWA();

// ── Routes ─────────────────────────────────────────────

// Status check
app.get("/status", (req, res) => {
  res.json({
    connected: isConnected,
    hasQR: !!currentQR,
  });
});

// QR Code (base64 image)
app.get("/qr", async (req, res) => {
  if (isConnected) return res.json({ connected: true });
  if (!currentQR)
    return res.json({
      waiting: true,
      message: "QR ready হয়নি, কয়েক সেকেন্ড অপেক্ষা করো",
    });

  try {
    const qrImage = await qrcode.toDataURL(currentQR);
    res.json({ qr: qrImage, raw: currentQR });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Pairing Code
app.post("/pair", async (req, res) => {
  const { phone } = req.body;
  if (!phone) return res.status(400).json({ error: "phone required" });
  if (isConnected) return res.json({ connected: true });
  if (!sock) return res.status(503).json({ error: "Socket not ready" });

  try {
    const digits = phone.replace(/\D/g, "");
    const code = await sock.requestPairingCode(digits);
    console.log(`🔑 Pairing code for +${digits}: ${code}`);
    res.json({ code });
  } catch (e) {
    console.error("Pair error:", e.message);
    res.status(500).json({ error: e.message || "Pairing code পাওয়া যায়নি" });
  }
});

// ── Fast Batch WA Check ──────────────────────────────────
app.post("/check", async (req, res) => {
  if (!isConnected || !sock) {
    return res.status(503).json({ error: "Not connected" });
  }

  const { numbers } = req.body;
  if (!numbers || !Array.isArray(numbers) || numbers.length === 0) {
    return res.status(400).json({ error: "numbers array required" });
  }

  const results = {};
  // Default সব false
  for (const n of numbers) results[n] = false;

  try {
    const cleaned = numbers.map((n) => n.replace(/\D/g, ""));

    // Baileys onWhatsApp — সব একসাথে check করে (দ্রুত)
    const waResults = await sock.onWhatsApp(...cleaned);

    if (Array.isArray(waResults)) {
      for (const r of waResults) {
        const num = r.jid.replace(/@s\.whatsapp\.net$/, "");
        const orig = numbers.find((n) => n.replace(/\D/g, "") === num);
        if (orig !== undefined) {
          results[orig] = r.exists === true;
        }
      }
    }

    res.json({ results });
  } catch (e) {
    console.error("Check error:", e.message);
    res.status(500).json({ error: e.message });
  }
});

// Disconnect / Logout
app.post("/disconnect", async (req, res) => {
  try {
    if (sock) {
      await sock.logout();
      sock = null;
    }
    isConnected = false;
    currentQR = null;
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ── Start ──────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`🚀 Baileys API Server চালু হয়েছে — Port: ${PORT}`);
});
