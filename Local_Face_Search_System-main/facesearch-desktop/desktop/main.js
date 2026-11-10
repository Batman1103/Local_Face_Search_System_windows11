const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  shell,
  Menu,
  Tray,
  nativeImage
} = require('electron');

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

let backend = null;
let backendReady = false;
let mainWindow = null;
let tray = null;
let quitting = false;

const PORT = 8765;

app.setAppUserModelId('com.facesearch.desktop');

function rootDir() {
  return app.isPackaged
    ? process.resourcesPath
    : path.resolve(__dirname, '..');
}

/*
 * Find the Python environment.
 *
 * Development:
 *   facesearch-desktop/.venv/bin/python
 *
 * Packaged app:
 *   ~/.config/FaceSearch/python-env/bin/python
 */
function pythonCommand() {
  const projectRoot = path.resolve(__dirname, '..');

  // Development virtual environment
  const projectVenv = path.join(projectRoot, '.venv');

  // Packaged application's Python environment
  const packagedVenv = path.join(
    app.getPath('userData'),
    'python-env'
  );

  let venv;

  if (
    process.platform !== 'win32' &&
    fs.existsSync(path.join(projectVenv, 'bin', 'python'))
  ) {
    // Development mode
    venv = projectVenv;
    console.log('[python] Using project virtual environment:', venv);
  } else if (
    process.platform === 'win32' &&
    fs.existsSync(path.join(projectVenv, 'Scripts', 'python.exe'))
  ) {
    // Development mode on Windows
    venv = projectVenv;
    console.log('[python] Using project virtual environment:', venv);
  } else {
    // Packaged application
    venv = packagedVenv;
    console.log('[python] Using packaged virtual environment:', venv);
  }

  const candidates =
    process.platform === 'win32'
      ? [
          path.join(venv, 'Scripts', 'python.exe'),
          'python',
          'python3'
        ]
      : [
          path.join(venv, 'bin', 'python'),
          'python3',
          'python'
        ];

  for (const candidate of candidates) {
    if (path.isAbsolute(candidate)) {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    } else {
      return candidate;
    }
  }

  return candidates[0];
}

function dataDirectory() {
  if (process.env.FACESEARCH_DATA_DIR) return process.env.FACESEARCH_DATA_DIR;
  if (process.platform === 'win32') {
    return path.join(process.env.LOCALAPPDATA || app.getPath('userData'), 'FaceSearch');
  }
  if (process.platform === 'darwin') {
    return path.join(app.getPath('home'), 'Library', 'Application Support', 'FaceSearch');
  }
  return path.join(app.getPath('home'), '.local', 'share', 'facesearch');
}

function startBackend() {
  const root = rootDir();
  const backendDir = path.join(root, 'backend');
  const packagedBackend = path.join(root, 'backend-dist', 'FaceSearchBackend.exe');
  const isBundledWindows = app.isPackaged && process.platform === 'win32' && fs.existsSync(packagedBackend);
  const py = pythonCommand();

  console.log('[backend] Root:', root);
  console.log('[backend] Directory:', backendDir);
  console.log('[backend] Runtime:', isBundledWindows ? packagedBackend : py);

  if (!isBundledWindows && !fs.existsSync(backendDir)) {
    console.error('[backend] Backend directory does not exist:', backendDir);
    return;
  }

  const command = isBundledWindows ? packagedBackend : py;
  const args = isBundledWindows ? [] : [
    '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1', '--port', String(PORT)
  ];

  backend = spawn(command, args, {
    cwd: isBundledWindows ? path.dirname(packagedBackend) : backendDir,
    env: {
      ...process.env,
      PYTHONPATH: backendDir,
      FACESEARCH_DATA_DIR: dataDirectory(),
      PYTHONUNBUFFERED: '1'
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true
  });

  backend.stdout.on('data', data => {
    console.log(`[backend] ${data}`);
  });

  backend.stderr.on('data', data => {
    console.log(`[backend] ${data}`);
  });

  backend.on('exit', (code, signal) => {
    backendReady = false;

    console.log(
      `[backend] Process exited. code=${code}, signal=${signal}`
    );

    if (!quitting && code !== 0) {
      console.error(
        `Backend exited with code ${code}`
      );
    }
  });

  backend.on('error', error => {
    console.error('[backend] Failed to start:', error);
  });
}

async function waitForBackend(timeoutMs = 600000) {
  const start = Date.now();

  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(
        `http://127.0.0.1:${PORT}/api/health`
      );

      if (response.ok) {
        backendReady = true;

        console.log('[backend] Backend is ready.');

        return true;
      }
    } catch (_) {
      // Backend is still starting.
    }

    await new Promise(resolve =>
      setTimeout(resolve, 400)
    );
  }

  return false;
}

function frontendIndex() {
  return path.join(
    rootDir(),
    'frontend',
    'dist',
    'index.html'
  );
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,

    minWidth: 900,
    minHeight: 700,

    backgroundColor: '#0b0e13',

    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),

      contextIsolation: true,

      nodeIntegration: false
    }
  });

  const dist = frontendIndex();

  if (fs.existsSync(dist)) {
    console.log('[frontend] Loading:', dist);

    await mainWindow.loadFile(dist);
  } else {
    console.log(
      '[frontend] Production build not found. Using Vite development server.'
    );

    await mainWindow.loadURL(
      'http://127.0.0.1:5173'
    );
  }

  mainWindow.on('close', event => {
    if (!quitting && tray) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createTray() {
  const iconPath = path.join(__dirname, 'assets', 'tray.png');
  const icon = fs.existsSync(iconPath)
    ? nativeImage.createFromPath(iconPath)
    : nativeImage.createEmpty();

  tray = new Tray(icon);

  tray.setToolTip('FaceSearch');

  const menu = Menu.buildFromTemplate([
    {
      label: 'Open FaceSearch',
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      }
    },

    {
      type: 'separator'
    },

    {
      label: 'Quit',
      click: () => {
        quitting = true;
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(menu);

  tray.on('double-click', () => {
    mainWindow?.show();
    mainWindow?.focus();
  });
}

ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(
    mainWindow,
    {
      properties: ['openDirectory']
    }
  );

  return result.canceled
    ? null
    : result.filePaths[0];
});

ipcMain.handle(
  'show-in-folder',
  async (_, filePath) => {
    if (
      filePath &&
      fs.existsSync(filePath)
    ) {
      await shell.showItemInFolder(filePath);
    }
  }
);

app.whenReady().then(async () => {
  console.log('====================================');
  console.log('        FaceSearch Desktop');
  console.log('====================================');

  startBackend();

  const ok = await waitForBackend();

  if (!ok) {
    dialog.showErrorBox(
      'FaceSearch backend failed to start',

      'The local backend could not start. Rebuild the Windows package using ' +
      'scripts\\build-windows.ps1, or check the backend startup logs.'
    );

    app.quit();

    return;
  }

  createTray();

  await createWindow();
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
  }
});

app.on('before-quit', () => {
  quitting = true;

  if (backend) {
    backend.kill();
    backend = null;
  }
});