import { app, BrowserWindow, shell, protocol, net, session } from 'electron';
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

let mainWindow: BrowserWindow | null = null;
let flaskProcess: ChildProcess | null = null;
let appiumProcess: ChildProcess | null = null;
let adbProcess: ChildProcess | null = null;

function getAndroidHome(isProd: boolean, workingDir: string): string {
  let androidHome = process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT || '';
  if (!androidHome || !fs.existsSync(path.join(androidHome, 'platform-tools'))) {
    const commonPaths = [
      path.join(os.homedir(), 'Android/Sdk'),
      '/usr/lib/android-sdk',
      '/opt/android-sdk',
      '/usr/local/android-sdk',
      path.join(workingDir, 'android-sdk')
    ];
    for (const p of commonPaths) {
      if (fs.existsSync(p) && fs.existsSync(path.join(p, 'platform-tools'))) {
        androidHome = p;
        break;
      }
    }
    if (!androidHome) {
      androidHome = isProd ? path.join(workingDir, 'android-sdk') : '/opt/android-sdk';
    }
  }
  return androidHome;
}

function getAppiumPath(): string {
  const commonPaths = [
    '/usr/local/bin/appium',
    '/usr/bin/appium',
    '/bin/appium'
  ];
  for (const p of commonPaths) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  try {
    const { execSync } = require('child_process');
    const prefix = execSync('npm config get prefix', { encoding: 'utf8' }).trim();
    const npmPath = path.join(prefix, 'bin', 'appium');
    if (fs.existsSync(npmPath)) {
      return npmPath;
    }
  } catch (e) {
    // ignore
  }
  return 'appium';
}

function loadEnv(workingDir: string) {
  const envPath = path.join(workingDir, '.env');
  if (fs.existsSync(envPath)) {
    try {
      const content = fs.readFileSync(envPath, 'utf8');
      for (const line of content.split('\n')) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
          const firstEq = trimmed.indexOf('=');
          if (firstEq !== -1) {
            const key = trimmed.substring(0, firstEq).trim();
            const val = trimmed.substring(firstEq + 1).trim().replace(/^['"]|['"]$/g, '');
            if (key) {
              process.env[key] = val;
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to parse .env file:', e);
    }
  }
}

// ── Spawn ADB, Appium, and Flask Python Backend ────────────────────────────────
function startServices() {
  const isProd = app.isPackaged;
  const appPath = app.getAppPath();
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');

  // Load environment variables from .env
  loadEnv(workingDir);

  const pythonScript = path.join(workingDir, 'frontend', 'app.py');
  const pythonExecutable = isProd ? path.join(workingDir, 'venv', 'bin', 'python3') : 'python3';
  const androidHome = getAndroidHome(isProd, workingDir);
  const adbPath = isProd ? (fs.existsSync(path.join(androidHome, 'platform-tools', 'adb')) ? path.join(androidHome, 'platform-tools', 'adb') : 'adb') : 'adb';
  const venvBin = isProd ? path.join(workingDir, 'venv', 'bin') : '';
  const jadxBin = isProd ? path.join(workingDir, 'jadx', 'bin') : '';
  const appiumHome = path.join(workingDir, '.appium');

  const env: any = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    ANDROID_HOME: androidHome,
    ANDROID_SDK_ROOT: androidHome,
    APPIUM_HOME: appiumHome
  };

  if (isProd) {
    const platformTools = path.join(androidHome, 'platform-tools');
    env.PATH = `${venvBin}:${platformTools}:${jadxBin}:${process.env.PATH}`;
  }

  console.log(`Spawning ADB: ${adbPath} start-server`);
  adbProcess = spawn(adbPath, ['start-server'], { env });
  adbProcess.on('close', (code) => console.log(`ADB start-server completed with code ${code}`));

  const logsDir = path.join(workingDir, 'logs');
  if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
  }
  const appiumLogPath = path.join(logsDir, 'appium.log');
  const pythonLogPath = path.join(logsDir, 'python.log');
  const appiumLogStream = fs.createWriteStream(appiumLogPath, { flags: 'a' });
  const pythonLogStream = fs.createWriteStream(pythonLogPath, { flags: 'a' });

  // Dynamically resolve port and address for Appium from APPIUM_SERVER_URL
  let appiumPort = '4723';
  let appiumAddress = '127.0.0.1';
  if (process.env.APPIUM_SERVER_URL) {
    try {
      const url = new URL(process.env.APPIUM_SERVER_URL);
      if (url.port) appiumPort = url.port;
      if (url.hostname && url.hostname !== 'localhost') {
        appiumAddress = url.hostname;
      }
    } catch (e) {
      // ignore
    }
  }

  const appiumPath = getAppiumPath();
  console.log(`Spawning Appium from ${appiumPath} on ${appiumAddress}:${appiumPort}`);
  appiumProcess = spawn(appiumPath, ['--address', appiumAddress, '--port', appiumPort, '--log-level', 'debug'], { env });
  appiumProcess.stdout?.pipe(appiumLogStream);
  appiumProcess.stderr?.pipe(appiumLogStream);
  appiumProcess.on('error', (err) => {
    console.error('Failed to start Appium process:', err);
    appiumLogStream.write(`ERROR: Failed to start Appium process: ${err.message}\n`);
  });
  appiumProcess.on('close', (code) => console.log(`Appium exited with code ${code}`));

  console.log(`Spawning Python: ${pythonExecutable} ${pythonScript}`);
  flaskProcess = spawn(pythonExecutable, [pythonScript], { cwd: workingDir, env });
  flaskProcess.stdout?.pipe(pythonLogStream);
  flaskProcess.stderr?.pipe(pythonLogStream);
  flaskProcess.on('close', (code) => console.log(`Python exited with code ${code}`));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    title: 'App Tag Auditor',
    backgroundColor: '#080c15',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // Disable renderer sandbox so Chromium can access /tmp for shared memory.
      // Without this, the compositor fails silently and the window stays black.
      sandbox: false,
      preload: path.join(__dirname, 'preload.js'),
    }
  });

  // Bypass Google OAuth embedded-browser block
  mainWindow.webContents.setUserAgent(
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
  );

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (
      url.startsWith('http://localhost:8501/api/results/download') ||
      !url.startsWith('http://localhost')
    ) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  // Load the app
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
    if (url.includes('code=')) {
      console.log('OAuth callback detected:', url);
    }
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

app.commandLine.appendSwitch('no-sandbox');
app.commandLine.appendSwitch('disable-setuid-sandbox');
app.commandLine.appendSwitch('disable-dev-shm-usage');

app.on('ready', () => {
  // Set global user agent to bypass Google OAuth embedded browser blocks
  session.defaultSession.setUserAgent(
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
  );

  // Serve Next.js static export via app:// protocol
  protocol.handle('app', async (request) => {
    try {
      const parsedUrl = new URL(request.url);
      let filePath = parsedUrl.pathname;

      if (filePath === '/' || filePath === '') filePath = '/index.html';

      const staticRoot = path.join(__dirname, '../renderer/out');
      let resolvedPath = path.join(staticRoot, filePath);

      if (fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isDirectory()) {
        resolvedPath = path.join(resolvedPath, 'index.html');
      } else if (!fs.existsSync(resolvedPath)) {
        // Try appending .html (Next.js static export without trailingSlash)
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

  startServices();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('quit', () => {
  if (flaskProcess) { console.log('Terminating Flask...'); flaskProcess.kill(); }
  if (appiumProcess) { console.log('Terminating Appium...'); appiumProcess.kill(); }

  const isProd = app.isPackaged;
  const appPath = app.getAppPath();
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');
  const androidHome = getAndroidHome(isProd, workingDir);
  const adbPath = isProd ? (fs.existsSync(path.join(androidHome, 'platform-tools', 'adb')) ? path.join(androidHome, 'platform-tools', 'adb') : 'adb') : 'adb';
  console.log('Stopping ADB server...');
  spawn(adbPath, ['kill-server']);
});
