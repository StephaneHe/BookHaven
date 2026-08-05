#!/usr/bin/env node
// ============================================================================
// bookhaven-watchdog.mjs — gardien de disponibilité du serveur BookHaven.
// ============================================================================
//
// Probe HTTP http://127.0.0.1:8097/ toutes les 10s.
// Toute réponse HTTP (quel que soit le code) = serveur vivant.
// Après 2 échecs consécutifs → appelle restart-bookhaven.cmd.
//
// Délai de grâce : 90s au démarrage (le serveur peut prendre ~60s à charger
// la DB). Pendant la grâce, les échecs de probe sont enregistrés mais
// n'incrémentent pas le compteur de relance.
//
// Stop propre : créer le fichier logs/watchdog.stop → le watchdog sort au
// prochain tick (supprime le fichier).
//
// Logs : C:\Dev\BookHaven\logs\watchdog.log
// ============================================================================

import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// Ensure logs dir exists
const LOGS_DIR = path.join(ROOT, 'logs');
try { fs.mkdirSync(LOGS_DIR, { recursive: true }); } catch {}

const LOG_FILE  = path.join(LOGS_DIR, 'watchdog.log');
const STOP_FILE = path.join(LOGS_DIR, 'watchdog.stop');
const RESTART_CMD = path.join(ROOT, 'scripts', 'restart-bookhaven.cmd');

const HEALTH_URL            = 'http://127.0.0.1:8097/';
const WATCHDOG_INTERVAL_MS  = 10_000;   // probe toutes les 10s
const PROBE_TIMEOUT_MS      = 5_000;    // timeout par probe
const CONSEC_FAILS_TO_RESTART = 2;      // 2 échecs consécutifs → restart
const RESTART_COOLDOWN_MS   = 90_000;   // pas plus d'1 restart par 90s
const STARTUP_GRACE_MS      = 90_000;   // pas de restart pendant les 90s post-démarrage

const startupTime = Date.now();
let consecFails   = 0;
let restartCount  = 0;
let lastRestartTs = 0;

// ---- Logging -------------------------------------------------------------

function log(line) {
  const stamped = `[${new Date().toISOString()}] ${line}\n`;
  try { fs.appendFileSync(LOG_FILE, stamped); } catch {}
  try { process.stderr.write(stamped); } catch {}
}

// ---- HTTP probe ----------------------------------------------------------

async function probe() {
  try {
    const res = await fetch(HEALTH_URL, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    return res.status > 0;
  } catch {
    return false;
  }
}

// ---- Restart logic -------------------------------------------------------

function triggerRestart() {
  const now = Date.now();

  if (now - lastRestartTs < RESTART_COOLDOWN_MS) {
    log(`restart skipped — cooldown actif (${Math.round((now - lastRestartTs) / 1000)}s depuis le dernier)`);
    return;
  }

  lastRestartTs = now;
  restartCount++;
  log(`SERVER DOWN — lancement restart-bookhaven.cmd (restart #${restartCount})`);

  const r = spawnSync(
    'cmd.exe',
    ['/c', RESTART_CMD],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: ROOT,
      timeout: 150_000,  // 2m30 max — le restart peut attendre 120s
    }
  );

  log(`restart exit=${r.status} (signal=${r.signal || 'none'})`);
  if (r.stdout && r.stdout.length)
    log(`restart stdout: ${r.stdout.toString().trim().split('\n').slice(-5).join(' | ')}`);
  if (r.stderr && r.stderr.length)
    log(`restart stderr: ${r.stderr.toString().trim().split('\n').slice(-3).join(' | ')}`);
}

// ---- Main tick -----------------------------------------------------------

async function tick() {
  // Stop file check
  if (fs.existsSync(STOP_FILE)) {
    log('fichier stop détecté — watchdog arrêté proprement');
    try { fs.unlinkSync(STOP_FILE); } catch {}
    process.exit(0);
  }

  const alive = await probe();
  const inGrace = (Date.now() - startupTime) < STARTUP_GRACE_MS;

  if (alive) {
    if (consecFails > 0)
      log(`serveur de nouveau disponible après ${consecFails} échec(s) consécutif(s)`);
    consecFails = 0;
  } else {
    if (inGrace) {
      const remaining = Math.round((STARTUP_GRACE_MS - (Date.now() - startupTime)) / 1000);
      log(`probe FAIL — délai de grâce actif (encore ~${remaining}s), pas de restart`);
    } else {
      consecFails++;
      log(`probe FAIL #${consecFails}`);
      if (consecFails >= CONSEC_FAILS_TO_RESTART) {
        triggerRestart();
        consecFails = 0; // laisser le temps au serveur de revenir
      }
    }
  }
}

// ---- Bootstrap -----------------------------------------------------------

log(`==== bookhaven-watchdog démarré pid=${process.pid} interval=${WATCHDOG_INTERVAL_MS}ms grace=${STARTUP_GRACE_MS}ms ====`);
log(`Probe URL : ${HEALTH_URL}`);
log(`Stop file : ${STOP_FILE}`);

// Premier tick immédiat, puis toutes les WATCHDOG_INTERVAL_MS
tick().catch(e => log(`tick error: ${e.message}`));
setInterval(() => {
  tick().catch(e => log(`tick error: ${e.message}`));
}, WATCHDOG_INTERVAL_MS);

// Robustesse : éviter que le watchdog lui-même tombe sur une exception non gérée
process.on('uncaughtException',  e => log(`UNCAUGHT dans watchdog: ${e.message}`));
process.on('unhandledRejection', r => log(`UNHANDLED dans watchdog: ${r}`));
