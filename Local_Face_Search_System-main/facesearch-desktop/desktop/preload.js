const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktop', {
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  showInFolder: (filePath) => ipcRenderer.invoke('show-in-folder', filePath)
});
