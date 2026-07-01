import { app, BrowserWindow, shell } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let flaskProcess: ChildProcess | null = null;

// ── Spawn Flask Python Backend ────────────────────────────────────────────────
function startFlaskBackend() {
  const isProd = app.isPackaged;
  const appPath = app.getAppPath();
  // In production (ASAR disabled), appPath is resources/app/, where frontend/app.py is copied directly.
  // In development, appPath is app_tag_auditor/electron-app/, and python files are in parent app_tag_auditor/.
  const workingDir = isProd ? appPath : path.resolve(appPath, '..');
  const pythonScript = path.join(workingDir, 'frontend', 'app.py');

  console.log(`Spawning Python process: python3 ${pythonScript} (Cwd: ${workingDir})`);

  flaskProcess = spawn('python3', [pythonScript], {
    cwd: workingDir,
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
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

app.on('ready', () => {
  startFlaskBackend();
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
});
