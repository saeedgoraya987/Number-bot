// ╔══════════════════════════════════════════════════════════════╗
// ║         EARNING HUB BOT — WhatsApp Check PATCH             ║
// ║  শুধু নিচের ৫টা step follow করো, পুরো file replace নয়     ║
// ╚══════════════════════════════════════════════════════════════╝

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// STEP 1: Install dependencies
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// terminal এ run করো:
//   npm install @whiskeysockets/baileys pino

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// STEP 2: line 6 এর পরে (imports এর শেষে) এই block যোগ করো
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const pino = require("pino");

const waSessions = {}; // { userId: { sock, isConnected } }
const WA_SESSIONS_DIR = path.join(DATA_DIR, "wa_sessions");
if (!fs.existsSync(WA_SESSIONS_DIR)) fs.mkdirSync(WA_SESSIONS_DIR, { recursive: true });

async function createWASession(userId, phoneNumber) {
  if (waSessions[userId]?.sock) {
    try { waSessions[userId].sock.end(); } catch(e) {}
    delete waSessions[userId];
  }
  const sessionDir = path.join(WA_SESSIONS_DIR, userId.toString());
  if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, pino({ level: "silent" })),
    },
    printQRInTerminal: false,
    logger: pino({ level: "silent" }),
    browser: ["Ubuntu", "Chrome", "20.0.04"],
    syncFullHistory: false,
  });

  waSessions[userId] = { sock, isConnected: false };
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", ({ connection, lastDisconnect }) => {
    if (connection === "open") {
      waSessions[userId].isConnected = true;
      console.log(`✅ WA connected: user ${userId}`);
    } else if (connection === "close") {
      waSessions[userId].isConnected = false;
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut || code === 401) {
        try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch(e) {}
        delete waSessions[userId];
        console.log(`🔴 WA logged out: user ${userId}`);
      }
    }
  });

  await new Promise(r => setTimeout(r, 3000));
  const code = await sock.requestPairingCode(phoneNumber.replace(/\D/g, ""));
  return code;
}

function isWAConnected(userId) {
  return waSessions[userId]?.isConnected === true;
}

async function checkWANumbers(userId, numbers) {
  if (!isWAConnected(userId)) return {};
  const sock = waSessions[userId].sock;
  const results = {};
  await Promise.all(numbers.map(async (num) => {
    try {
      const jid = num.replace(/\D/g, "") + "@s.whatsapp.net";
      const [res] = await sock.onWhatsApp(jid);
      results[num] = res?.exists === true;
    } catch(e) { results[num] = null; }
  }));
  return results;
}

async function restoreWASessions() {
  if (!fs.existsSync(WA_SESSIONS_DIR)) return;
  for (const uid of fs.readdirSync(WA_SESSIONS_DIR)) {
    const sessionDir = path.join(WA_SESSIONS_DIR, uid);
    if (!fs.existsSync(path.join(sessionDir, "creds.json"))) continue;
    try {
      const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
      const { version } = await fetchLatestBaileysVersion();
      const sock = makeWASocket({
        version,
        auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, pino({ level: "silent" })) },
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["Ubuntu", "Chrome", "20.0.04"],
        syncFullHistory: false,
      });
      waSessions[uid] = { sock, isConnected: false };
      sock.ev.on("creds.update", saveCreds);
      sock.ev.on("connection.update", ({ connection, lastDisconnect }) => {
        if (connection === "open") {
          waSessions[uid].isConnected = true;
          console.log(`✅ WA restored: user ${uid}`);
        } else if (connection === "close") {
          waSessions[uid].isConnected = false;
          const code = lastDisconnect?.error?.output?.statusCode;
          if (code === DisconnectReason.loggedOut || code === 401) {
            try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch(e) {}
            delete waSessions[uid];
          }
        }
      });
      console.log(`🔄 Restoring WA session: user ${uid}`);
    } catch(e) { console.error(`WA restore failed for ${uid}:`, e.message); }
  }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// STEP 3: bot handlers এর যেকোনো জায়গায় এই 3টা action যোগ করো
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

bot.action("wa_connect", async (ctx) => {
  await ctx.answerCbQuery();
  ctx.session.waConnectState = "waiting_number";
  await ctx.reply(
    "📱 *WhatsApp Connect*\n\n" +
    "তোমার WhatsApp নম্বর দাও *(country code সহ)*:\n" +
    "Example: `8801712345678`\n\n" +
    "⚠️ এই নম্বরের WA দিয়ে number check হবে।",
    { parse_mode: "Markdown" }
  );
});

bot.action("wa_status", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id.toString();
  const connected = isWAConnected(userId);
  await ctx.reply(
    connected
      ? "✅ *WhatsApp connected!*\n\nNumber assign হলে WA status দেখাবে।"
      : "🔴 *WhatsApp connected নেই।*\n\nConnect করলে number check হবে।",
    {
      parse_mode: "Markdown",
      reply_markup: {
        inline_keyboard: connected
          ? [[{ text: "🔴 Disconnect WA", callback_data: "wa_disconnect" }]]
          : [[{ text: "📱 Connect WhatsApp", callback_data: "wa_connect" }]]
      }
    }
  );
});

bot.action("wa_disconnect", async (ctx) => {
  await ctx.answerCbQuery();
  const userId = ctx.from.id.toString();
  if (waSessions[userId]?.sock) {
    try { waSessions[userId].sock.end(); } catch(e) {}
    delete waSessions[userId];
  }
  const sessionDir = path.join(WA_SESSIONS_DIR, userId.toString());
  try { fs.rmSync(sessionDir, { recursive: true, force: true }); } catch(e) {}
  await ctx.reply("🔴 *WhatsApp disconnected.*", { parse_mode: "Markdown" });
});

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// STEP 4: TEXT HANDLER এ waConnectState যোগ করো
//
// bot.on("text", ...) এর ভেতরে, line 3753 এর পরে
// (const userId = ctx.from.id.toString(); এর পরে)
// এই block যোগ করো:
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    // ── WA Connect: নম্বর input ──
    if (ctx.session.waConnectState === "waiting_number") {
      ctx.session.waConnectState = null;
      const phone = text.replace(/\D/g, "");
      if (phone.length < 10 || phone.length > 15) {
        return await ctx.reply("❌ Invalid number. Country code সহ দাও।\nExample: `8801712345678`", { parse_mode: "Markdown" });
      }
      const loadMsg = await ctx.reply("⏳ *Connecting...*", { parse_mode: "Markdown" });
      try {
        const rawCode = await createWASession(userId, phone);
        const code = rawCode.match(/.{1,4}/g)?.join("-") || rawCode;
        await ctx.telegram.deleteMessage(ctx.chat.id, loadMsg.message_id).catch(() => {});
        await ctx.reply(
          `🔑 *Pairing Code*\n\n` +
          `\`${code}\`\n\n` +
          `📋 *Steps:*\n` +
          `1. WhatsApp খোলো\n` +
          `2. Settings → Linked Devices\n` +
          `3. Link a Device → *Link with phone number*\n` +
          `4. উপরের code টা enter করো\n\n` +
          `⏰ ১ মিনিটের মধ্যে expire হবে।`,
          {
            parse_mode: "Markdown",
            reply_markup: {
              inline_keyboard: [
                [{ text: "✅ Check Status", callback_data: "wa_status" }],
                [{ text: "🔄 New Code", callback_data: "wa_connect" }]
              ]
            }
          }
        );
      } catch(e) {
        console.error("WA connect error:", e);
        await ctx.telegram.deleteMessage(ctx.chat.id, loadMsg.message_id).catch(() => {});
        await ctx.reply("❌ Connection failed. কিছুক্ষণ পর try করো।");
      }
      return;
    }

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// STEP 5: ৩টা জায়গায় numbersText replace করো
//
// জায়গাগুলো:
//   A) select_country handler   (line ~1232)
//   B) get_new_numbers handler  (line ~1309)
//   C) Change Numbers handler   (line ~1381)
//
// প্রতিটায় এই পুরনো code:
//
//   let numbersText = '';
//   numbers.forEach((num, i) => {
//     numbersText += `${i + 1}. \`+${num}\`\n`;
//   });
//
// এই নতুন code দিয়ে replace করো:
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    const waConnected = isWAConnected(userId);
    const waResults = await checkWANumbers(userId, numbers);

    let numbersText = '';
    numbers.forEach((num, i) => {
      let waIcon = '';
      if (waConnected) {
        waIcon = waResults[num] === true ? ' ✅' : waResults[num] === false ? ' ❌' : ' ⬜';
      }
      numbersText += `${i + 1}. \`+${num}\`${waIcon}\n`;
    });

// এবং inline_keyboard array তে শেষে এই line যোগ করো
// (শুধু WA connected না থাকলে button দেখাবে):

    ...(waConnected ? [] : [[{ text: '📱 Connect WhatsApp', callback_data: 'wa_connect' }]]),

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// STEP 6: startBot() এর ভেতরে await bot.launch() এর আগে যোগ করো:
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    await restoreWASessions();

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DONE! এটুকুই। নিচে select_country handler এর
// পুরো modified version দেওয়া হলো reference এর জন্য:
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

bot.action(/^select_country:(.+):(.+)$/, async (ctx) => {
  try {
    await ctx.answerCbQuery();
    const serviceId = ctx.match[1];
    const countryCode = ctx.match[2];
    const userId = ctx.from.id.toString();
    const numberCount = settings.defaultNumberCount;

    const now = Date.now();
    const timeSinceLast = now - ctx.session.lastNumberTime;
    const cooldown = settings.cooldownSeconds * 1000;

    if (timeSinceLast < cooldown && (ctx.session.currentNumbers || []).length > 0) {
      const remaining = Math.ceil((cooldown - timeSinceLast) / 1000);
      await ctx.answerCbQuery();
      return await ctx.reply(`⏳ *${remaining} সেকেন্ড অপেক্ষা করুন।*`, { parse_mode: "Markdown" });
    }

    const numbers = getMultipleNumbersByCountryAndService(countryCode, serviceId, userId, numberCount);

    if (numbers.length === 0) {
      return await ctx.answerCbQuery(`❌ Not enough numbers available.`, { show_alert: true });
    }

    if ((ctx.session.currentNumbers || []).length > 0) {
      (ctx.session.currentNumbers || []).forEach(num => {
        if (activeNumbers[num]) delete activeNumbers[num];
      });
      saveActiveNumbers();
    }

    ctx.session.currentNumbers = numbers;
    ctx.session.currentService = serviceId;
    ctx.session.currentCountry = countryCode;
    ctx.session.lastNumberTime = now;

    const country  = countries[countryCode];
    const service  = services[serviceId];
    const otpPrice = getOtpPriceForCountry(countryCode);

    // ── WA CHECK (নতুন) ──
    const waConnected = isWAConnected(userId);
    const waResults = await checkWANumbers(userId, numbers);

    let numbersText = '';
    numbers.forEach((num, i) => {
      let waIcon = '';
      if (waConnected) {
        waIcon = waResults[num] === true ? ' ✅' : waResults[num] === false ? ' ❌' : ' ⬜';
      }
      numbersText += `${i + 1}. \`+${num}\`${waIcon}\n`;
    });
    // ── END WA CHECK ──

    const message =
      `✅ *${numbers.length} Number(s) Assigned!*\n\n` +
      `${service.icon} *Service:* ${service.name}\n` +
      `${country.flag} *Country:* ${country.name}\n` +
      `💵 *Earnings per OTP:* ${otpPrice.toFixed(2)} taka\n\n` +
      `📞 *Numbers:*\n${numbersText}\n` +
      `📌 Use this number in the OTP Group.\n` +
      `OTP will appear here and balance will be updated automatically.`;

    const sentMessage = await ctx.editMessageText(message, {
      parse_mode: 'Markdown',
      reply_markup: {
        inline_keyboard: [
          [{ text: '📨 Open OTP Group', url: OTP_GROUP }],
          [{ text: '🔄 Get New Numbers', callback_data: `get_new_numbers:${serviceId}:${countryCode}` }],
          [{ text: '🔙 Service List', callback_data: 'back_to_services' }],
          ...(waConnected ? [] : [[{ text: '📱 Connect WhatsApp', callback_data: 'wa_connect' }]]),
        ]
      }
    });

    if (sentMessage && sentMessage.message_id) {
      ctx.session.lastMessageId = sentMessage.message_id;
      ctx.session.lastChatId = ctx.chat.id;
    }

  } catch (error) {
    console.error("Country selection error:", error);
    await ctx.answerCbQuery("❌ Error getting numbers", { show_alert: true });
  }
});
