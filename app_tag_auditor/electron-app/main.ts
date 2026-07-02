import { app, BrowserWindow, shell } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let flaskProcess: ChildProcess | null = null;

let appiumProcess: ChildProcess | null = null;
let adbProcess: ChildProcess | null = null;

// ── Spawn ADB, Appium, and Flask Python Backend ────────────────────────────────
function startServices() {
  const isProd = app.isPackaged;
  const appPath = app.getAppPath();
  // In production (ASAR disabled), appPath is resources/app/, where frontend/app.py is copied directly.
  // In development, appPath is app_tag_auditor/electron-app/, and python files are in parent app_tag_auditor/.
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');
  const pythonScript = path.join(workingDir, 'frontend', 'app.py');

  // Resolve paths for production env
  const pythonExecutable = isProd ? path.join(workingDir, 'venv', 'bin', 'python3') : 'python3';
  const androidHome = isProd ? path.join(workingDir, 'android-sdk') : (process.env.ANDROID_HOME || '/opt/android-sdk');
  const adbPath = isProd ? path.join(androidHome, 'platform-tools', 'adb') : 'adb';
  const venvBin = isProd ? path.join(workingDir, 'venv', 'bin') : '';
  const jadxBin = isProd ? path.join(workingDir, 'jadx', 'bin') : '';

  // Setup environment variables
  const env: any = { 
    ...process.env, 
    PYTHONUNBUFFERED: '1',
    ANDROID_HOME: androidHome,
    ANDROID_SDK_ROOT: androidHome
  };

  if (isProd) {
    const platformTools = path.join(androidHome, 'platform-tools');
    env.PATH = `${venvBin}:${platformTools}:${jadxBin}:${process.env.PATH}`;
  }

  // 1. Spawn ADB start-server
  console.log(`Spawning ADB: ${adbPath} start-server (Cwd: ${workingDir})`);
  adbProcess = spawn(adbPath, ['start-server'], { env });
  adbProcess.on('close', (code) => {
    console.log(`ADB start-server completed with code ${code}`);
  });

  // 2. Spawn Appium
  console.log(`Spawning Appium on port 4723 (Cwd: ${workingDir})`);
  appiumProcess = spawn('appium', ['--address', '127.0.0.1', '--log-level', 'error'], { env });
  
  appiumProcess.stdout?.on('data', (data) => {
    console.log(`[Appium Stdout]: ${data}`);
  });
  appiumProcess.stderr?.on('data', (data) => {
    console.error(`[Appium Stderr]: ${data}`);
  });
  appiumProcess.on('close', (code) => {
    console.log(`Appium process exited with code ${code}`);
  });

  // 3. Spawn Flask python process
  console.log(`Spawning Python process: ${pythonExecutable} ${pythonScript} (Cwd: ${workingDir})`);
  flaskProcess = spawn(pythonExecutable, [pythonScript], {
    cwd: workingDir,
    env
  });

  flaskProcess.stdout?.on('data', (data) => {
    console.log(`[Python Stdout]: ${data}`);
  });

  flaskProcess.stderr?.on('data', (data) => {
    console.error(`[Python Stderr]: ${data}`);
  });

  flaskProcess.on('close', (code) => {
    console.log(`Python process exited with code ${code}`);
  });
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
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // Handle external links (e.g. download results link) using the system default browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://localhost:8501/api/results/download') || !url.startsWith('http://localhost')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  // Load the web app
  if (app.isPackaged) {
    mainWindow.loadFile(path.join(__dirname, '../renderer/out/index.html'));
  } else {
    mainWindow.loadURL('http://localhost:3000');
  }

  // Intercept redirects to google oauth redirect uri so we don't open inside Electron frame
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (url.includes('code=')) {
      // It is the OAuth callback code!
      console.log('OAuth Callback Detected:', url);
      // Let it load inside our view, page.tsx will capture query params and check profile
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.commandLine.appendSwitch("no-sandbox");
app.commandLine.appendSwitch("disable-setuid-sandbox");

app.on('ready', () => {
  startServices();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  if (flaskProcess) {
    console.log('Terminating Python process...');
    flaskProcess.kill();
  }
  if (appiumProcess) {
    console.log('Terminating Appium process...');
    appiumProcess.kill();
  }
  
  // Shut down ADB server in production to release USB device lock
  const isProd = app.isPackaged;
  const appPath = app.getAppPath();
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');
  const androidHome = isProd ? path.join(workingDir, 'android-sdk') : (process.env.ANDROID_HOME || '/opt/android-sdk');
  const adbPath = isProd ? path.join(androidHome, 'platform-tools', 'adb') : 'adb';
  console.log('Stopping ADB server...');
  spawn(adbPath, ['kill-server']);
});
