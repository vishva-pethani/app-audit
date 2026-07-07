import { app, BrowserWindow, shell, protocol, net, session, ipcMain } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import { pathToFileURL } from 'url';
import * as fs from 'fs';
import * as os from 'os';

// Must be called before app is ready
app.disableHardwareAcceleration();

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } }
]);

const isWindows = process.platform === 'win32';
const pathSep  = isWindows ? ';' : ':';

let mainWindow: BrowserWindow | null = null;
let flaskProcess:  ChildProcess | null = null;
let appiumProcess: ChildProcess | null = null;
let adbProcess:    ChildProcess | null = null;

// ── Helper: resolve Python executable inside the bundled venv ─────────────────
function getPythonExecutable(isProd: boolean, workingDir: string): string {
  if (!isProd) return isWindows ? 'python' : 'python3';
  return isWindows
    ? path.join(workingDir, 'venv', 'Scripts', 'python.exe')
    : path.join(workingDir, 'venv', 'bin', 'python3');
}

// ── Helper: resolve the Android SDK home directory ────────────────────────────
function getAndroidHome(isProd: boolean, workingDir: string): string {
  let androidHome = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || '';
  if (!androidHome || !fs.existsSync(path.join(androidHome, 'platform-tools'))) {
    const candidates = [
      // Windows defaults
      path.join(os.homedir(), 'AppData', 'Local', 'Android', 'Sdk'),
      'C:\\Android\\Sdk',
      'C:\\Android\\sdk',
      // Linux / macOS defaults
      path.join(os.homedir(), 'Android', 'Sdk'),
      '/usr/lib/android-sdk',
      '/opt/android-sdk',
      '/usr/local/android-sdk',
      // bundled
      path.join(workingDir, 'android-sdk'),
    ];
    for (const p of candidates) {
      if (fs.existsSync(p) && fs.existsSync(path.join(p, 'platform-tools'))) {
        androidHome = p;
        break;
      }
    }
    if (!androidHome) {
      androidHome = isProd ? path.join(workingDir, 'android-sdk') : (isWindows ? 'C:\\Android\\Sdk' : '/opt/android-sdk');
    }
  }
  return androidHome;
}

// ── Helper: locate the Appium binary ─────────────────────────────────────────
function getAppiumPath(): string {
  if (isWindows) {
    const winCandidates = [
      path.join(os.homedir(), 'AppData', 'Roaming', 'npm', 'appium.cmd'),
      path.join(os.homedir(), 'AppData', 'Roaming', 'npm', 'appium'),
      'C:\\Program Files\\nodejs\\appium.cmd',
    ];
    for (const p of winCandidates) {
      if (fs.existsSync(p)) return p;
    }
    try {
      const { execSync } = require('child_process');
      const prefix = execSync('npm config get prefix', { encoding: 'utf8', shell: true }).trim();
      const npmCmd = path.join(prefix, 'appium.cmd');
      if (fs.existsSync(npmCmd)) return npmCmd;
    } catch (_) { /* ignore */ }
    return 'appium.cmd';
  } else {
    const unixCandidates = [
      '/usr/local/bin/appium',
      '/usr/bin/appium',
      '/bin/appium',
    ];
    for (const p of unixCandidates) {
      if (fs.existsSync(p)) return p;
    }
    try {
      const { execSync } = require('child_process');
      const prefix = execSync('npm config get prefix', { encoding: 'utf8' }).trim();
      const npmBin = path.join(prefix, 'bin', 'appium');
      if (fs.existsSync(npmBin)) return npmBin;
    } catch (_) { /* ignore */ }
    return 'appium';
  }
}

// ── Helper: parse .env into process.env ──────────────────────────────────────
function loadEnv(workingDir: string) {
  const envPath = path.join(workingDir, '.env');
  if (!fs.existsSync(envPath)) return;
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#')) {
        const firstEq = trimmed.indexOf('=');
        if (firstEq !== -1) {
          const key = trimmed.substring(0, firstEq).trim();
          const val = trimmed.substring(firstEq + 1).trim().replace(/^['\"]|['\"]$/g, '');
          if (key) process.env[key] = val;
        }
      }
    }
  } catch (e) {
    console.error('Failed to parse .env file:', e);
  }
}

// ── Spawn ADB, Appium, and Flask Python Backend ───────────────────────────────
function startServices() {
  const isProd     = app.isPackaged;
  const appPath    = app.getAppPath();
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');

  loadEnv(workingDir);

  const pythonScript     = path.join(workingDir, 'frontend', 'app.py');
  const pythonExecutable = getPythonExecutable(isProd, workingDir);
  const androidHome      = getAndroidHome(isProd, workingDir);
  const adbExe           = isWindows ? 'adb.exe' : 'adb';
  const adbFullPath      = path.join(androidHome, 'platform-tools', adbExe);
  const adbPath          = isProd && fs.existsSync(adbFullPath) ? adbFullPath : adbExe;
  const appiumHome       = path.join(workingDir, '.appium');

  // Build venv bin and jadx bin dirs (platform-aware)
  const venvBin = isProd
    ? (isWindows ? path.join(workingDir, 'venv', 'Scripts') : path.join(workingDir, 'venv', 'bin'))
    : '';
  const jadxBin = isProd ? path.join(workingDir, 'jadx', 'bin') : '';

  const env: any = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    ANDROID_HOME:     androidHome,
    ANDROID_SDK_ROOT: androidHome,
    APPIUM_HOME:      appiumHome,
  };

  if (isProd) {
    const platformTools = path.join(androidHome, 'platform-tools');
    const extraPaths    = [venvBin, platformTools, jadxBin].filter(Boolean).join(pathSep);
    env.PATH = `${extraPaths}${pathSep}${process.env.PATH}`;
  }

  // ── ADB start-server ───────────────────────────────────────────────────────
  console.log(`Spawning ADB: ${adbPath} start-server`);
  adbProcess = spawn(adbPath, ['start-server'], {
    env,
    shell: isWindows,  // Windows needs shell:true to resolve .exe / .cmd
  });
  adbProcess.on('close', (code) => console.log(`ADB start-server completed with code ${code}`));

  // ── Log streams ───────────────────────────────────────────────────────────
  const logsDir = path.join(workingDir, 'logs');
  if (!fs.existsSync(logsDir)) fs.mkdirSync(logsDir, { recursive: true });
  const appiumLogStream = fs.createWriteStream(path.join(logsDir, 'appium.log'), { flags: 'a' });
  const pythonLogStream = fs.createWriteStream(path.join(logsDir, 'python.log'), { flags: 'a' });

  // ── Resolve Appium address/port from APPIUM_SERVER_URL ───────────────────
  let appiumPort    = '4723';
  let appiumAddress = '127.0.0.1';
  if (process.env.APPIUM_SERVER_URL) {
    try {
      const url = new URL(process.env.APPIUM_SERVER_URL);
      if (url.port)     appiumPort    = url.port;
      if (url.hostname && url.hostname !== 'localhost') appiumAddress = url.hostname;
    } catch (_) { /* ignore */ }
  }

  const appiumPath = getAppiumPath();
  console.log(`Spawning Appium from ${appiumPath} on ${appiumAddress}:${appiumPort}`);
  appiumProcess = spawn(
    appiumPath,
    ['--address', appiumAddress, '--port', appiumPort, '--log-level', 'debug'],
    { env, shell: isWindows }
  );
  appiumProcess.stdout?.pipe(appiumLogStream);
  appiumProcess.stderr?.pipe(appiumLogStream);
  appiumProcess.on('error', (err) => {
    console.error('Failed to start Appium process:', err);
    appiumLogStream.write(`ERROR: Failed to start Appium process: ${err.message}\n`);
  });
  appiumProcess.on('close', (code) => console.log(`Appium exited with code ${code}`));

  // ── Flask / Python backend ────────────────────────────────────────────────
  console.log(`Spawning Python: ${pythonExecutable} ${pythonScript}`);
  flaskProcess = spawn(pythonExecutable, [pythonScript], {
    cwd: workingDir,
    env,
    shell: isWindows,
  });
  flaskProcess.stdout?.pipe(pythonLogStream);
  flaskProcess.stderr?.pipe(pythonLogStream);
  flaskProcess.on('close', (code) => console.log(`Python exited with code ${code}`));
}

// ── Create the main Electron window ──────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'App Tag Auditor',
    backgroundColor: '#080c15',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.webContents.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
  );

  const flaskPort = process.env.FLASK_PORT || '8501';
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (
      url.startsWith(`http://localhost:${flaskPort}/api/results/download`) ||
      !url.startsWith('http://localhost')
    ) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  if (app.isPackaged) {
    mainWindow.loadURL('app:///index.html');
  } else {
    mainWindow.loadURL('http://localhost:3000');
  }

  if (!app.isPackaged) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.webContents.on('console-message', (_e, level, msg, line, src) => {
    console.log(`[Renderer L${level}] ${msg} (${src}:${line})`);
  });

  mainWindow.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error(`[Renderer] did-fail-load: ${code} ${desc} — ${url}`);
  });

  mainWindow.webContents.on('will-navigate', (_e, url) => {
    if (url.includes('code=')) console.log('OAuth callback detected:', url);
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── Chromium flags (no-sandbox needed on some Linux setups) ──────────────────
app.commandLine.appendSwitch('no-sandbox');
app.commandLine.appendSwitch('disable-setuid-sandbox');
app.commandLine.appendSwitch('disable-dev-shm-usage');

app.on('ready', () => {
  session.defaultSession.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
  );

  protocol.handle('app', async (request) => {
    try {
      const parsedUrl = new URL(request.url);
      let filePath = parsedUrl.pathname;
      if (filePath === '/' || filePath === '') filePath = '/index.html';

      const staticRoot   = path.join(__dirname, '../renderer/out');
      let resolvedPath   = path.join(staticRoot, filePath);

      if (fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory()) {
        resolvedPath = path.join(resolvedPath, 'index.html');
      } else if (!fs.existsSync(resolvedPath)) {
        const htmlPath = resolvedPath + '.html';
        if (fs.existsSync(htmlPath)) resolvedPath = htmlPath;
      }

      console.log(`[app://] ${parsedUrl.pathname} → ${resolvedPath}`);
      return net.fetch(pathToFileURL(resolvedPath).toString());
    } catch (err: any) {
      console.error(`[app://] Error: ${err.message} for ${request.url}`);
      return new Response(`Error: ${err.message}`, { status: 500 });
    }
  });

  ipcMain.on('get-api-base-url', (event) => {
    const flaskPort = process.env.FLASK_PORT || '8501';
    event.returnValue = `http://localhost:${flaskPort}`;
  });

  startServices();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('quit', () => {
  if (flaskProcess)  { console.log('Terminating Flask...');  flaskProcess.kill();  }
  if (appiumProcess) { console.log('Terminating Appium...'); appiumProcess.kill(); }

  const isProd     = app.isPackaged;
  const appPath    = app.getAppPath();
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');
  const androidHome = getAndroidHome(isProd, workingDir);
  const adbExe     = isWindows ? 'adb.exe' : 'adb';
  const adbFullPath = path.join(androidHome, 'platform-tools', adbExe);
  const adbPath     = isProd && fs.existsSync(adbFullPath) ? adbFullPath : adbExe;
  console.log('Stopping ADB server...');
  spawn(adbPath, ['kill-server'], { shell: isWindows });
});
