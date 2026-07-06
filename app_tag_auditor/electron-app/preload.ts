import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  getApiBaseUrl: () => ipcRenderer.sendSync('get-api-base-url')
});
